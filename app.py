"""
퇴직 정산용 연차 계산기 (근로기준법 제60조 기반)
────────────────────────────────────────
매년 연차를 정산하는 기업 실무에 맞춘 퇴직 정산 전용 Streamlit 웹 앱

법적 근거:
  - 근로기준법 제60조 (연차 유급휴가)
  - 고용노동부 행정해석 (회계연도 기준 운영 시 퇴사 시점 입사일 기준 재정산 의무)
"""

import calendar
import math
from datetime import date

import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta

# ─────────────────────────────────────────────────────────────────────────────
# 페이지 설정
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="퇴직 정산용 연차 계산기",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
div[data-testid="metric-container"] {
    background-color: #f0f2f6;
    border-radius: 10px;
    padding: 12px 16px;
    margin: 4px 0;
}
div[data-testid="stExpander"] details summary p {
    font-size: 1.05rem;
    font-weight: 600;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# 핵심 계산 함수 (근기법 제60조)
# ─────────────────────────────────────────────────────────────────────────────

def _safe_fiscal_date(year: int, month: int, day: int) -> date:
    """유효하지 않은 날짜(예: 2월 30일)를 해당 월 말일로 보정"""
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def annual_leave_days(years_completed: int) -> int:
    """
    완성된 근속연수에 따른 연차 발생일수 (최대 25일)
    근기법 §60①④: 3년차부터 매 2년마다 +1일 가산
    """
    if years_completed < 1:
        return 0
    base = 15
    extra = max(0, (years_completed - 1) // 2)   # 3년차: +1, 5년차: +2, …
    return min(base + extra, 25)


def _leave_note(years_completed: int) -> str:
    """발생 내역 비고 문자열"""
    if years_completed < 1:
        return "1년 미만 월차 (§60②)"
    extra = max(0, (years_completed - 1) // 2)
    days  = min(15 + extra, 25)
    note  = "기본 15일"
    if extra > 0:
        note += f" + 가산 {extra}일 = {days}일"
    return note


def calc_hire_basis(hire_date: date, ref_date: date) -> list[dict]:
    """
    [입사일 기준] 연차 발생 내역 계산
      - 1년 미만: 매월 1일 (최대 11일)
      - 1년 이상: 주년마다 annual_leave_days() 적용
    """
    if ref_date <= hire_date:
        return []

    records = []
    one_year = hire_date + relativedelta(years=1)

    # 1년 미만 월별 연차
    for m in range(1, 12):
        accrual_date = hire_date + relativedelta(months=m)
        if accrual_date > ref_date or accrual_date >= one_year:
            break
        records.append({
            "발생 시점": f"입사 {m}개월차",
            "발생일자":  accrual_date,
            "발생일수":  1,
            "산정 근거": "1년 미만 월차 (§60②)",
        })

    # 1년 이상 주년별 연차
    y = 1
    while True:
        anniversary = hire_date + relativedelta(years=y)
        if anniversary > ref_date:
            break
        records.append({
            "발생 시점": f"입사 {y}주년",
            "발생일자":  anniversary,
            "발생일수":  annual_leave_days(y),
            "산정 근거": _leave_note(y),
        })
        y += 1

    return records


def calc_fiscal_basis(
    hire_date: date, ref_date: date,
    fiscal_month: int = 1, fiscal_day: int = 1,
) -> list[dict]:
    """
    [회계연도 기준] 연차 발생 내역 계산
      - 첫 회계연도 전: 월별 연차 동일 적용
      - 첫 회계연도: 비례 부여 (15 × 근무일수/365, 절사)
      - 이후 회계연도: 근속연수 기반 정규 연차
    """
    if ref_date <= hire_date:
        return []

    records = []
    first_fiscal = _safe_fiscal_date(hire_date.year, fiscal_month, fiscal_day)
    if first_fiscal <= hire_date:
        first_fiscal = _safe_fiscal_date(hire_date.year + 1, fiscal_month, fiscal_day)

    one_year_from_hire = hire_date + relativedelta(years=1)
    cutoff = min(first_fiscal, one_year_from_hire)   # 더 이른 시점까지만 월차 적용

    # 첫 회계연도 또는 1주년 이전까지 월별 연차
    for m in range(1, 12):
        accrual_date = hire_date + relativedelta(months=m)
        if accrual_date >= cutoff or accrual_date > ref_date:
            break
        records.append({
            "발생 시점": f"입사 {m}개월차",
            "발생일자":  accrual_date,
            "발생일수":  1,
            "산정 근거": "1년 미만 월차 (§60②)",
        })

    # 회계연도별 연차
    current_fiscal = first_fiscal
    while current_fiscal <= ref_date:
        days_since_hire  = (current_fiscal - hire_date).days
        years_completed  = relativedelta(current_fiscal, hire_date).years

        if days_since_hire < 365:
            # 첫 회계연도: 비례 계산 (소수점 절사)
            raw          = 15 * days_since_hire / 365
            proportional = math.floor(raw)
            records.append({
                "발생 시점": f"{current_fiscal.year}년 회계일",
                "발생일자":  current_fiscal,
                "발생일수":  proportional,
                "산정 근거": f"비례: 15 × {days_since_hire}일/365 = {raw:.1f}일 (행정해석)",
            })
        else:
            # 2년차 이상: 근속연수 기반 정규 연차
            records.append({
                "발생 시점": f"{current_fiscal.year}년 회계일",
                "발생일자":  current_fiscal,
                "발생일수":  annual_leave_days(years_completed),
                "산정 근거": _leave_note(years_completed),
            })

        current_fiscal = _safe_fiscal_date(current_fiscal.year + 1, fiscal_month, fiscal_day)

    return records


def calc_leave_pay(monthly_wage: float, weekly_hours: float, unused_days: float) -> dict:
    """
    미사용 연차 수당 계산
      시간당 통상임금 = 월 통상임금 ÷ 209h
      1일 소정근로시간 = (주 근로시간 / 40) × 8h  (단시간 근로자 비례)
      1일 통상임금 = 시간당 × 1일 소정근로시간
    """
    hourly_wage = monthly_wage / 209
    daily_hours = (weekly_hours / 40) * 8
    daily_wage  = hourly_wage * daily_hours
    total_pay   = daily_wage * unused_days
    return {
        "hourly_wage": hourly_wage,
        "daily_hours": daily_hours,
        "daily_wage":  daily_wage,
        "total_pay":   total_pay,
    }


def records_to_df(records: list[dict]) -> pd.DataFrame:
    """발생 내역 리스트 → 표시용 DataFrame"""
    if not records:
        return pd.DataFrame(columns=["발생 시점", "발생일자", "발생일수", "산정 근거"])
    df = pd.DataFrame(records)
    df["발생일자"] = df["발생일자"].apply(lambda d: d.strftime("%Y-%m-%d"))
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 사이드바 입력폼
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ 퇴직 정산 설정")

    # ── 근무 기간 ─────────────────────────────────────────────────────────
    st.subheader("📆 근무 기간")
    hire_date = st.date_input("입사일", value=date(2022, 1, 1), max_value=date.today())
    ref_date  = st.date_input("퇴사일 (정산 기준일)", value=date.today())

    # ── 연차 사용/정산 현황 ───────────────────────────────────────────────
    st.divider()
    st.subheader("📝 재직 중 연차 처리 현황")
    st.caption("실제 사용 일수 + 매년 수당으로 정산받은 일수의 **총합**을 입력하세요.")
    used_days = st.number_input(
        "기사용 + 기정산 연차 합계 (일)",
        min_value=0.0, value=0.0, step=0.5, format="%.1f",
        help="예) 휴가 10일 사용 + 연말 수당 정산 5일 → 15일 입력",
    )

    # ── 수당 산정 ─────────────────────────────────────────────────────────
    st.divider()
    st.subheader("💰 수당 산정 (선택)")
    weekly_hours = st.slider(
        "1주 소정근로시간", min_value=1, max_value=40, value=40, format="%d시간",
        help="단시간 근로자는 실제 주 근무시간 입력",
    )
    if weekly_hours < 40:
        st.info(f"단시간 근로자\n1일 소정근로시간 = **{(weekly_hours/40*8):.2f}시간**")
    monthly_wage = st.number_input(
        "월 통상임금 (원)", min_value=0, value=0, step=100_000, format="%d",
        help="입력 시 미사용 연차수당 자동 계산",
    )

# 입력 유효성 검사
if ref_date <= hire_date:
    st.error("⚠️ 퇴사일은 입사일보다 이후여야 합니다.")
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# 계산 실행
# ─────────────────────────────────────────────────────────────────────────────
# 회계연도 기준일: 1월 1일 고정 (사내 규정)
FISCAL_MONTH, FISCAL_DAY = 1, 1

hire_records   = calc_hire_basis(hire_date, ref_date)
fiscal_records = calc_fiscal_basis(hire_date, ref_date, FISCAL_MONTH, FISCAL_DAY)

hire_total     = sum(r["발생일수"] for r in hire_records)
fiscal_total   = sum(r["발생일수"] for r in fiscal_records)
hire_remaining   = max(0.0, hire_total   - used_days)
fiscal_remaining = max(0.0, fiscal_total - used_days)

# 유리한 기준 판별
if hire_total >= fiscal_total:
    favorable_basis  = "입사일 기준"
    final_remain     = hire_remaining
    need_recount     = hire_total > fiscal_total   # 재정산 필요 여부
    extra_days       = hire_total - fiscal_total
else:
    favorable_basis  = "회계연도 기준"
    final_remain     = fiscal_remaining
    need_recount     = False
    extra_days       = fiscal_total - hire_total

# 수당 계산 (월 통상임금 입력 시)
pay = calc_leave_pay(monthly_wage, weekly_hours, final_remain) if monthly_wage > 0 else None

# 근속기간 문자열
tenure = relativedelta(ref_date, hire_date)
tenure_parts = []
if tenure.years:  tenure_parts.append(f"{tenure.years}년")
if tenure.months: tenure_parts.append(f"{tenure.months}개월")
tenure_parts.append(f"{tenure.days}일")
tenure_str = " ".join(tenure_parts)


# ─────────────────────────────────────────────────────────────────────────────
# 메인 화면 헤더
# ─────────────────────────────────────────────────────────────────────────────
st.title("⚖️ 퇴직 정산용 연차 비교 계산기")
st.caption(
    f"**입사일** {hire_date.strftime('%Y-%m-%d')} │ "
    f"**퇴사일** {ref_date.strftime('%Y-%m-%d')} │ "
    f"**총 근속기간** {tenure_str}"
)


# ─────────────────────────────────────────────────────────────────────────────
# 상단 요약 메트릭 (4개 — 한눈에 파악)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("#### 📊 정산 현황 요약")
k1, k2, k3, k4 = st.columns(4)

k1.metric("🏢 회계연도 기준 총 발생", f"{fiscal_total:.0f}일")

# 입사일 기준 메트릭: 회계연도와 차이를 delta로 표시
diff_label = (
    f"회계연도보다 {int(hire_total - fiscal_total)}일 많음" if hire_total > fiscal_total
    else "두 기준 동일" if hire_total == fiscal_total
    else f"회계연도보다 {int(fiscal_total - hire_total)}일 적음"
)
k2.metric(
    "⚖️ 입사일 기준 총 발생", f"{hire_total:.0f}일",
    delta=diff_label,
    delta_color="inverse" if hire_total > fiscal_total else "off",
)

k3.metric("✅ 기사용 + 기정산 합계", f"{used_days:.1f}일")

# 최종 잔여 + 수당 총액 표시
if pay and final_remain > 0:
    k4.metric(
        "💡 최종 정산 대상 연차", f"{final_remain:.1f}일",
        delta=f"수당: {pay['total_pay']:,.0f}원", delta_color="off",
    )
else:
    k4.metric(
        "💡 최종 정산 대상 연차", f"{final_remain:.1f}일",
        delta=f"기준: {favorable_basis}", delta_color="off",
    )

st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# 좌우 비교 테이블 (항상 양쪽 표시)
# ─────────────────────────────────────────────────────────────────────────────
def render_column(
    col, title: str, records: list[dict],
    total: float, remaining: float, is_favorable: bool,
):
    """연차 발생 내역 컬럼 렌더링"""
    with col:
        badge = "　✅ **[유리]**" if is_favorable else ""
        st.subheader(title + badge)

        if records:
            # 내용에 맞게 높이 동적 계산 (최소 150, 최대 420)
            h = min(max(150, 55 + len(records) * 35), 420)
            st.dataframe(records_to_df(records), use_container_width=True, hide_index=True, height=h)
        else:
            st.info("발생 내역이 없습니다.")

        m1, m2 = st.columns(2)
        m1.metric("총 발생일수", f"{total:.0f}일")
        m2.metric(
            "최종 미정산 잔여", f"{remaining:.1f}일",
            delta=f"기사용/정산 {used_days:.1f}일 차감", delta_color="off",
        )


col_l, col_r = st.columns(2, gap="large")
render_column(
    col_l, "🏢 회계연도 기준 (사내 규정)",
    fiscal_records, fiscal_total, fiscal_remaining,
    is_favorable=(favorable_basis == "회계연도 기준"),
)
render_column(
    col_r, "⚖️ 입사일 기준 (법정 최소한도)",
    hire_records, hire_total, hire_remaining,
    is_favorable=(favorable_basis == "입사일 기준"),
)


# ─────────────────────────────────────────────────────────────────────────────
# 최종 퇴직 정산 결론
# ─────────────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("💡 최종 퇴직 정산 결론")

if need_recount:
    # 입사일 기준이 더 많아 재정산 필요
    st.error(
        f"🚨 **재정산 필요**: 입사일 기준 발생 연차({hire_total:.0f}일)가 "
        f"회계연도 기준({fiscal_total:.0f}일)보다 **{extra_days:.0f}일** 더 많습니다.\n\n"
        f"퇴직 시에는 근로자에게 유리한 **입사일 기준**으로 재정산해야 합니다. "
        f"(고용노동부 행정해석, 근로조건지도과-2261)"
    )
    # 실제 추가 지급이 필요한 경우만 표시
    shortfall = hire_remaining - fiscal_remaining
    if shortfall > 0:
        st.warning(
            f"⚠️ 회계연도 기준 잔여 **{fiscal_remaining:.1f}일** → "
            f"입사일 기준 잔여 **{hire_remaining:.1f}일**: "
            f"**{shortfall:.1f}일분 추가 지급 필요**"
        )

elif fiscal_total > hire_total:
    st.success(
        f"✅ 회계연도 기준({fiscal_total:.0f}일)이 입사일 기준({hire_total:.0f}일)보다 "
        f"**{extra_days:.0f}일** 더 유리합니다. 기존 사내 기준으로 그대로 정산하면 됩니다."
    )
else:
    st.info(
        f"ℹ️ 두 기준 모두 동일합니다 ({hire_total:.0f}일). "
        "어느 기준으로 정산해도 무방합니다."
    )

# 결론 메트릭 행
rc1, rc2, rc3 = st.columns(3)
rc1.metric("적용 정산 기준", favorable_basis)
rc2.metric("최종 미정산 잔여 연차", f"{final_remain:.1f}일")

if pay:
    if final_remain > 0:
        rc3.metric("💴 지급해야 할 연차수당", f"{pay['total_pay']:,.0f}원")

        with st.expander("📊 연차수당 산출 상세"):
            st.markdown(f"""
| 항목 | 계산식 | 결과 |
|------|--------|------|
| 월 통상임금 | 입력값 | **{monthly_wage:,}원** |
| 시간당 통상임금 | {monthly_wage:,}원 ÷ 209시간 | **{pay['hourly_wage']:,.2f}원** |
| 1일 소정근로시간 | ({weekly_hours}h ÷ 40h) × 8h | **{pay['daily_hours']:.2f}시간** |
| **1일 통상임금** | {pay['hourly_wage']:,.2f}원 × {pay['daily_hours']:.2f}h | **{pay['daily_wage']:,.0f}원** |
| 정산 대상 연차 | {favorable_basis} 기준 잔여 | **{final_remain:.1f}일** |
| **연차수당 총액** | {pay['daily_wage']:,.0f}원 × {final_remain:.1f}일 | **{pay['total_pay']:,.0f}원** |
            """)
            if weekly_hours < 40:
                st.warning(
                    f"⚠️ 단시간 근로자 비례 적용: "
                    f"1일 소정근로시간 **{pay['daily_hours']:.2f}시간** 기준으로 계산되었습니다."
                )
            st.caption("※ 209시간 = (주 40h + 주휴 8h) × 4.345주")
    else:
        rc3.metric("💴 연차수당", "0원")
        st.success("🎉 미사용 잔여 연차가 없습니다. 연차수당을 지급하지 않아도 됩니다.")
else:
    rc3.metric("💴 연차수당", "—")
    st.caption("💡 사이드바에 **월 통상임금**을 입력하면 지급해야 할 연차수당이 자동 계산됩니다.")


# ─────────────────────────────────────────────────────────────────────────────
# 인사담당자 퇴직 정산 실무 Check Point
# ─────────────────────────────────────────────────────────────────────────────
st.divider()
with st.expander("📋 인사담당자 퇴직 정산 실무 Check Point", expanded=False):
    st.markdown("""
    #### 1. 매년 연차수당 정산을 해온 경우의 처리
    - 본 계산기는 근속 기간 전체의 **총 발생 연차**를 산출합니다.
    - 매년 말 미사용 연차를 수당으로 정산해 왔다면, 해당 정산 일수 + 실제 사용 일수의 합을
      사이드바 **[기사용 + 기정산 합계]**에 입력해야 최종 정산값이 정확합니다.

    #### 2. 퇴사 시 회계연도 vs 입사일 재정산 의무 (중요)
    - **고용노동부 행정해석 (근로조건지도과-2261)**: 회계연도 단위로 연차를 부여했더라도
      퇴직 시에는 반드시 입사일 기준과 비교하여, 입사일 기준이 더 유리하면 **차액을 추가 지급**해야 합니다.
    - 미지급 시 **임금체불**에 해당합니다. 본 계산기의 🚨/✅ 결론을 반드시 확인하세요.

    #### 3. 단시간 근로자의 연차수당 정산
    - 1일 소정근로시간 = (주 소정근로시간 ÷ 40) × 8시간으로 비례 계산합니다.
    - 주 20시간 근로자: 연차 1일 = **4시간분** 임금 지급 (8시간 기준 적용 시 과다 지급)

    #### 4. 연차수당 지급 시기
    - 퇴직일로부터 **14일 이내** 지급 의무 (근기법 제36조)
    - 지연 지급 시 연 **20%** 지연이자 발생 가능
    """)
    st.info(
        "📌 본 계산기는 참고용입니다. "
        "분쟁 발생 시 공인노무사 또는 고용노동부(☎ 1350) 문의를 권장합니다."
    )
