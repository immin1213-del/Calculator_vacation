"""
퇴직 정산용 연차 계산기 (근로기준법 제60조 기반)
────────────────────────────────────────
매년 1월 1일 기준으로 연차를 정산하는 기업 실무 전용.
퇴사연도 이전의 모든 연차는 이미 정산(지급)된 것으로 자동 처리하며,
올해 사용한 일수만 입력하면 최종 지급액을 자동 산출합니다.

법적 근거:
  - 근로기준법 제60조 (연차 유급휴가)
  - 고용노동부 행정해석 (회계연도 기준 운영 시 퇴사 시점 입사일 기준 재정산 의무)
"""

from datetime import date

import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta

# ─────────────────────────────────────────────────────────────────────────────
# 상수: 회계연도 기준일 (1월 1일 고정)
# ─────────────────────────────────────────────────────────────────────────────
FISCAL_MONTH, FISCAL_DAY = 1, 1

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

def annual_leave_days(years_completed: int) -> int:
    """
    완성된 근속연수에 따른 연차 발생일수 (최대 25일).
    근기법 §60①④: 3년차부터 매 2년마다 +1일 가산.
    """
    if years_completed < 1:
        return 0
    extra = max(0, (years_completed - 1) // 2)
    return min(15 + extra, 25)


def _leave_note(years_completed: int) -> str:
    """발생 내역 비고 문자열."""
    if years_completed < 1:
        return "1년 미만 월차 (§60②)"
    extra = max(0, (years_completed - 1) // 2)
    days  = min(15 + extra, 25)
    return "기본 15일" + (f" + 가산 {extra}일 = {days}일" if extra else "")


def calc_hire_basis(hire_date: date, ref_date: date) -> list[dict]:
    """
    [입사일 기준] 연차 발생 내역.
      ① 1년 미만: 매 1개월 개근 시 1일 (최대 11일)
      ② 1년 이상: 입사 N주년에 annual_leave_days(N)일
    """
    if ref_date <= hire_date:
        return []

    records = []
    one_year = hire_date + relativedelta(years=1)

    for m in range(1, 12):
        d = hire_date + relativedelta(months=m)
        if d > ref_date or d >= one_year:
            break
        records.append({"발생 시점": f"입사 {m}개월차", "발생일자": d,
                         "발생일수": 1, "산정 근거": "1년 미만 월차 (§60②)"})

    y = 1
    while True:
        d = hire_date + relativedelta(years=y)
        if d > ref_date:
            break
        records.append({"발생 시점": f"입사 {y}주년", "발생일자": d,
                         "발생일수": annual_leave_days(y), "산정 근거": _leave_note(y)})
        y += 1

    return records


def calc_fiscal_basis(hire_date: date, ref_date: date) -> list[dict]:
    """
    [회계연도(1/1) 기준] 연차 발생 내역.
      ① 입사 후 1주년까지: 매 1개월 개근 시 1일 월차 (§60②, 입사 다음 해 포함)
      ② 첫 회계연도(1/1): 비례 부여 (15 × 근무일수/365, 소수점 유지)
      ③ 이후 매 1/1: 근속연수 기반 정규 연차
    """
    if ref_date <= hire_date:
        return []

    records = []

    # 입사 후 첫 번째 1월 1일 탐색
    first_fiscal = date(hire_date.year, FISCAL_MONTH, FISCAL_DAY)
    if first_fiscal <= hire_date:
        first_fiscal = date(hire_date.year + 1, FISCAL_MONTH, FISCAL_DAY)

    one_year_from_hire = hire_date + relativedelta(years=1)

    # 1년 미만 기간 전체 월별 연차 (입사 다음 해 포함, 1주년 전까지)
    for m in range(1, 12):
        d = hire_date + relativedelta(months=m)
        if d >= one_year_from_hire or d > ref_date:
            break
        records.append({"발생 시점": f"입사 {m}개월차", "발생일자": d,
                         "발생일수": 1, "산정 근거": "1년 미만 월차 (§60②)"})

    # 회계연도별 연차 (매년 1월 1일)
    cur = first_fiscal
    while cur <= ref_date:
        days_since = (cur - hire_date).days
        years_done  = relativedelta(cur, hire_date).years

        if days_since < 365:
            raw = round(15 * days_since / 365, 2)
            records.append({"발생 시점": f"{cur.year}년 1/1",
                             "발생일자": cur, "발생일수": raw,
                             "산정 근거": f"비례: 15×{days_since}일/365={raw}일"})
        else:
            days = annual_leave_days(years_done)
            records.append({"발생 시점": f"{cur.year}년 1/1",
                             "발생일자": cur, "발생일수": days,
                             "산정 근거": _leave_note(years_done)})

        cur = date(cur.year + 1, FISCAL_MONTH, FISCAL_DAY)

    records.sort(key=lambda r: r["발생일자"])
    return records


def calc_leave_pay(monthly_wage: float, weekly_hours: float, days: float) -> dict:
    """미사용 연차 수당 계산 (시간당 통상임금 = 월급 ÷ 209h)."""
    hourly = monthly_wage / 209
    daily_h = (weekly_hours / 40) * 8
    daily_w = hourly * daily_h
    return {"hourly": hourly, "daily_h": daily_h, "daily_w": daily_w, "total": daily_w * days}


def to_df(records: list[dict], settled_before: date) -> pd.DataFrame:
    """발생 내역 → 표시용 DataFrame (정산 구분 컬럼 포함)."""
    if not records:
        return pd.DataFrame(columns=["발생 시점", "발생일자", "발생일수", "정산 구분", "산정 근거"])
    df = pd.DataFrame(records)
    df["정산 구분"] = df["발생일자"].apply(
        lambda d: "✅ 기정산" if d < settled_before else "🔴 이번 정산"
    )
    df["발생일자"] = df["발생일자"].apply(lambda d: d.strftime("%Y-%m-%d"))
    return df[["발생 시점", "발생일자", "발생일수", "정산 구분", "산정 근거"]]


# ─────────────────────────────────────────────────────────────────────────────
# 사이드바
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ 퇴직 정산 설정")

    st.subheader("📆 근무 기간")
    hire_date = st.date_input("입사일", value=date(2022, 1, 1), max_value=date.today())
    ref_date  = st.date_input("퇴사일", value=date.today())

    st.divider()
    st.subheader("📝 올해 연차 사용 현황")
    st.caption(
        f"**{date.today().year}년 1월 1일 이전** 연차는 이미 정산된 것으로 자동 처리됩니다. "
        "올해 실제로 쉰 날수만 입력하세요."
    )
    current_year_used = st.number_input(
        f"{date.today().year}년 실제 사용 연차일수",
        min_value=0.0, value=0.0, step=0.5, format="%.1f",
        help="1월 1일부터 퇴사일까지 휴가로 사용한 일수. 연말 정산분은 입력 불필요.",
    )

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

# 유효성 검사
if ref_date <= hire_date:
    st.error("⚠️ 퇴사일은 입사일보다 이후여야 합니다.")
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# 계산 실행
# ─────────────────────────────────────────────────────────────────────────────
hire_records   = calc_hire_basis(hire_date, ref_date)
fiscal_records = calc_fiscal_basis(hire_date, ref_date)

hire_total   = sum(r["발생일수"] for r in hire_records)
fiscal_total = sum(r["발생일수"] for r in fiscal_records)

# 퇴사연도 1월 1일 = 과거 기정산 기준선
settled_cutoff = date(ref_date.year, FISCAL_MONTH, FISCAL_DAY)

# 과거 기정산분: settled_cutoff 이전에 발생한 회계연도 기준 연차 합계 (자동)
past_fiscal_paid   = sum(r["발생일수"] for r in fiscal_records if r["발생일자"] < settled_cutoff)
# 올해 부여분: settled_cutoff 이후 회계연도 기준 연차 (당해년도 1/1 지급분)
current_fiscal_grant = sum(r["발생일수"] for r in fiscal_records if r["발생일자"] >= settled_cutoff)
# 올해 입사일 기준 발생분 (주년일이 올해인 경우)
current_hire_grant = sum(r["발생일수"] for r in hire_records if r["발생일자"] >= settled_cutoff)

# 법정 재정산: 입사일 기준 총계가 회계연도 총계보다 많으면 그 차이를 추가 지급
need_recount  = hire_total > fiscal_total
recount_days  = max(0.0, hire_total - fiscal_total)

# 최종 정산 공식:
#   max(입사일기준 총계, 회계연도기준 총계) - 과거기정산 - 올해사용
favorable_total  = max(hire_total, fiscal_total)
final_remain     = max(0.0, favorable_total - past_fiscal_paid - current_year_used)
favorable_basis  = "입사일 기준" if hire_total >= fiscal_total else "회계연도 기준"

# 수당 계산
pay = calc_leave_pay(monthly_wage, weekly_hours, final_remain) if monthly_wage > 0 else None

# 근속기간 문자열
tenure = relativedelta(ref_date, hire_date)
parts  = []
if tenure.years:  parts.append(f"{tenure.years}년")
if tenure.months: parts.append(f"{tenure.months}개월")
parts.append(f"{tenure.days}일")
tenure_str = " ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# 메인 화면
# ─────────────────────────────────────────────────────────────────────────────
st.title("⚖️ 퇴직 정산용 연차 비교 계산기")
st.caption(
    f"**입사일** {hire_date.strftime('%Y-%m-%d')} │ "
    f"**퇴사일** {ref_date.strftime('%Y-%m-%d')} │ "
    f"**근속기간** {tenure_str} │ "
    f"회계연도 기준일: **매년 1월 1일** (고정)"
)

# ─────────────────────────────────────────────────────────────────────────────
# 상단 요약 메트릭 4개
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("#### 📊 정산 현황 요약")
k1, k2, k3, k4 = st.columns(4)

k1.metric(
    "📦 과거 기정산 (자동)",
    f"{past_fiscal_paid:.2f}일",
    delta=f"{ref_date.year - 1}년 이전 회계연도 기준",
    delta_color="off",
)
k2.metric(
    f"📋 {ref_date.year}년 부여 연차",
    f"{current_fiscal_grant:.2f}일",
    delta=f"{ref_date.year}년 1월 1일 기준",
    delta_color="off",
)
k3.metric(
    f"✅ {ref_date.year}년 사용 연차",
    f"{current_year_used:.1f}일",
    delta="사용자 입력",
    delta_color="off",
)
if pay and final_remain > 0:
    k4.metric(
        "💡 최종 정산 대상",
        f"{final_remain:.2f}일",
        delta=f"수당: {pay['total']:,.0f}원",
        delta_color="off",
    )
else:
    k4.metric(
        "💡 최종 정산 대상",
        f"{final_remain:.2f}일",
        delta=f"기준: {favorable_basis}",
        delta_color="off",
    )

st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# 좌우 비교 테이블 (항상 양쪽)
# ─────────────────────────────────────────────────────────────────────────────
def render_column(col, title: str, records: list[dict], total: float, is_favorable: bool):
    with col:
        badge = "　✅ **[유리]**" if is_favorable else ""
        st.subheader(title + badge)
        if records:
            h = min(max(160, 55 + len(records) * 35), 440)
            st.dataframe(to_df(records, settled_cutoff),
                         use_container_width=True, hide_index=True, height=h)
        else:
            st.info("발생 내역이 없습니다.")
        st.metric("총 발생일수", f"{total:.2f}일")


col_l, col_r = st.columns(2, gap="large")
render_column(col_l, "🏢 회계연도 기준 (사내 규정, 1/1)",
              fiscal_records, fiscal_total, not need_recount)
render_column(col_r, "⚖️ 입사일 기준 (법정 최소한도)",
              hire_records, hire_total, need_recount)


# ─────────────────────────────────────────────────────────────────────────────
# 최종 퇴직 정산 결론
# ─────────────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("💡 최종 퇴직 정산 결론")

# 재정산 상태 메시지
if need_recount:
    st.error(
        f"🚨 **재정산 필요**: 입사일 기준({hire_total:.0f}일)이 회계연도 기준({fiscal_total:.2f}일)보다 "
        f"**{recount_days:.2f}일 더 많습니다.**\n\n"
        "퇴직 시에는 근로자에게 유리한 입사일 기준으로 재정산해야 합니다. "
        "(고용노동부 행정해석, 근로조건지도과-2261)"
    )
else:
    st.success(
        f"✅ 회계연도 기준({fiscal_total:.2f}일)이 입사일 기준({hire_total:.0f}일) 이상입니다. "
        "기존 사내 기준대로 정산하면 됩니다."
    )

# 정산 계산표
st.markdown("##### 📋 정산 내역 계산표")

rows = [
    ("회계연도 기준 총 발생", f"{fiscal_total:.2f}일", ""),
    ("입사일 기준 총 발생",   f"{hire_total:.0f}일",   ""),
    ("━" * 20, "━" * 6, ""),
    ("과거 기정산 차감",      f"- {past_fiscal_paid:.2f}일",
     f"{ref_date.year-1}년까지 회계연도 기준 자동 정산"),
]
if need_recount:
    rows.append(("법정 재정산 추가분", f"+ {recount_days:.2f}일",
                 "입사일 기준 초과분 (추가 지급 의무)"))
rows += [
    (f"{ref_date.year}년 사용 연차 차감", f"- {current_year_used:.1f}일", "올해 실제 사용"),
    ("━" * 20, "━" * 6, ""),
    ("✅ 최종 지급 대상 연차", f"**{final_remain:.2f}일**", f"기준: {favorable_basis}"),
]
if pay and final_remain > 0:
    rows.append(("💴 지급해야 할 연차수당", f"**{pay['total']:,.0f}원**",
                 f"1일 통상임금 {pay['daily_w']:,.0f}원 × {final_remain:.2f}일"))

df_calc = pd.DataFrame(rows, columns=["항목", "금액/일수", "비고"])
st.dataframe(df_calc, use_container_width=True, hide_index=True)

# 수당 상세
if pay and final_remain > 0:
    with st.expander("📊 연차수당 산출 상세"):
        st.markdown(f"""
| 항목 | 계산식 | 결과 |
|------|--------|------|
| 월 통상임금 | 입력값 | **{monthly_wage:,}원** |
| 시간당 통상임금 | {monthly_wage:,}원 ÷ 209시간 | **{pay['hourly']:,.2f}원** |
| 1일 소정근로시간 | ({weekly_hours}h ÷ 40h) × 8h | **{pay['daily_h']:.2f}시간** |
| **1일 통상임금** | {pay['hourly']:,.2f}원 × {pay['daily_h']:.2f}h | **{pay['daily_w']:,.0f}원** |
| 정산 대상 연차 | {favorable_basis} 기준 | **{final_remain:.2f}일** |
| **연차수당 총액** | {pay['daily_w']:,.0f}원 × {final_remain:.2f}일 | **{pay['total']:,.0f}원** |
        """)
        if weekly_hours < 40:
            st.warning(
                f"⚠️ 단시간 근로자 비례 적용: 1일 소정근로시간 **{pay['daily_h']:.2f}시간** 기준"
            )
        st.caption("※ 209시간 = (주 40h + 주휴 8h) × 4.345주")
elif monthly_wage <= 0:
    st.caption("💡 사이드바에 **월 통상임금**을 입력하면 연차수당이 자동 계산됩니다.")
elif final_remain <= 0:
    st.success("🎉 미사용 잔여 연차가 없습니다. 연차수당을 지급하지 않아도 됩니다.")


# ─────────────────────────────────────────────────────────────────────────────
# 인사담당자 Check Point
# ─────────────────────────────────────────────────────────────────────────────
st.divider()
with st.expander("📋 인사담당자 퇴직 정산 실무 Check Point", expanded=False):
    st.markdown(f"""
    #### 1. 과거 연도 자동 기정산 처리 방식
    - 본 계산기는 **{ref_date.year}년 1월 1일 이전**에 회계연도 기준으로 발생한 연차를 이미 지급한 것으로 자동 처리합니다.
    - 실제 과거 지급 기록이 다를 경우 담당자가 직접 확인 후 결과를 참고하세요.

    #### 2. 퇴사 시 법정 재정산 의무 (중요)
    - **고용노동부 행정해석 (근로조건지도과-2261)**: 회계연도 기준 총계보다 입사일 기준 총계가 크면,
      그 차이만큼 **추가 지급 의무**가 발생합니다.
    - 미지급 시 **임금체불**에 해당합니다.

    #### 3. 단시간 근로자 연차수당
    - 1일 통상임금 = (월급 ÷ 209h) × (주 근무시간 ÷ 40 × 8h)
    - 주 20시간 근로자: 연차 1일 = **4시간분** 임금 (8시간 기준 아님)

    #### 4. 연차수당 지급 시기
    - 퇴직일로부터 **14일 이내** 지급 의무 (근기법 제36조)
    - 지연 지급 시 연 **20%** 지연이자 발생 가능
    """)
    st.info("📌 본 계산기는 참고용입니다. 분쟁 발생 시 공인노무사 또는 고용노동부(☎ 1350) 문의 권장.")
