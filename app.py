import streamlit as st
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
import datetime
import plotly.graph_objects as go
import os

# 페이지 설정
st.set_page_config(
    page_title="주식 & 지수 수익률 비교",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 제목 및 소개
st.markdown("<h1 style='color: #8AB4F8; margin-bottom: 10px;'>국내외 주식 & 지수 수익률 비교</h1>", unsafe_allow_html=True)
st.markdown("""
<div style="color: #BDC1C6; font-size: 1.0rem; margin-bottom: 20px; line-height: 1.6;">
한국 및 미국 주식과 주요 지수의 누적 수익률을 비교할 수 있는 대시보드입니다.<br/>
시작일의 자산 가격을 <b>100%</b> 기준으로 설정하여 종료일까지의 상대적인 변동 추이를 백분율(%)로 보여줍니다.
</div>
""", unsafe_allow_html=True)

# --- 데이터 캐싱 및 매핑 로직 ---

@st.cache_data(ttl=86400)  # 24시간 동안 캐시 유지
def load_krx_data():
    """KRX 종목 목록을 가져와서 코드가 포함된 데이터프레임을 반환합니다."""
    cache_file = "krx_cache.csv"
    try:
        # 실시간 데이터 로드 시도
        df = fdr.StockListing('KRX')
        df_cleaned = df[['Code', 'Name', 'Market']].copy()
        # 로컬 백업 파일 저장
        df_cleaned.to_csv(cache_file, index=False, encoding='utf-8-sig')
        return df_cleaned
    except Exception as e:
        # 실시간 로드 실패 시 로컬 캐시 시도
        if os.path.exists(cache_file):
            try:
                return pd.read_csv(cache_file, dtype={'Code': str})
            except Exception:
                pass
        
        # 캐시 파일도 없는 경우, 주요 대형주 폴백 데이터 반환
        fallback_data = [
            {"Code": "005930", "Name": "삼성전자", "Market": "KOSPI"},
            {"Code": "000660", "Name": "SK하이닉스", "Market": "KOSPI"},
            {"Code": "005935", "Name": "삼성전자우", "Market": "KOSPI"},
            {"Code": "035720", "Name": "카카오", "Market": "KOSPI"},
            {"Code": "035420", "Name": "NAVER", "Market": "KOSPI"},
            {"Code": "005380", "Name": "현대차", "Market": "KOSPI"},
            {"Code": "000270", "Name": "기아", "Market": "KOSPI"},
            {"Code": "207940", "Name": "삼성바이오로직스", "Market": "KOSPI"},
            {"Code": "068270", "Name": "셀트리온", "Market": "KOSPI"},
            {"Code": "051910", "Name": "LG화학", "Market": "KOSPI"},
            {"Code": "373220", "Name": "LG에너지솔루션", "Market": "KOSPI"},
            {"Code": "006400", "Name": "삼성SDI", "Market": "KOSPI"},
            {"Code": "247540", "Name": "에코프로비엠", "Market": "KOSDAQ"},
            {"Code": "086520", "Name": "에코프로", "Market": "KOSDAQ"},
        ]
        return pd.DataFrame(fallback_data)

@st.cache_data(ttl=86400)
def get_us_stock_name(symbol):
    """yfinance를 이용해 미국 주식의 기업명을 가져옵니다."""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        name = info.get('shortName') or info.get('longName') or symbol
        # 특수문자나 너무 긴 이름 축소
        if name and len(name) > 25:
            name = name[:22] + "..."
        return name
    except Exception:
        return symbol

def resolve_ticker(input_str, krx_df):
    """
    사용자가 입력한 종목명이나 코드를 검출하여 yfinance 티커와 한글/영문 표시 이름으로 변환합니다.
    Returns: (resolved_ticker, display_name)
    """
    input_clean = input_str.strip()
    if not input_clean:
        return None, None

    # 1. 한국 주식 한글명으로 검색
    name_match = krx_df[krx_df['Name'].str.lower() == input_clean.lower()]
    if not name_match.empty:
        code = name_match.iloc[0]['Code']
        market = name_match.iloc[0]['Market']
        name = name_match.iloc[0]['Name']
        suffix = '.KS' if market == 'KOSPI' else '.KQ'
        return f"{code}{suffix}", name

    # 2. 한국 주식 코드로 검색 (소수점 접미사 제거 후 비교)
    code_clean = input_clean
    if code_clean.endswith('.KS') or code_clean.endswith('.KQ'):
        code_clean = code_clean[:-3]

    if code_clean.isdigit() and len(code_clean) == 6:
        code_match = krx_df[krx_df['Code'] == code_clean]
        if not code_match.empty:
            market = code_match.iloc[0]['Market']
            name = code_match.iloc[0]['Name']
            suffix = '.KS' if market == 'KOSPI' else '.KQ'
            return f"{code_clean}{suffix}", name
        else:
            # KRX 목록에 없지만 한국 코드 형식인 경우 디폴트로 .KS 설정
            return f"{code_clean}.KS", f"한국주식({code_clean})"

    # 3. 미국 주식 또는 기타 해외 티커로 인식
    symbol = input_clean.upper()
    
    # 지수 예외 처리 (수동 입력 시 대응)
    index_map = {
        '^KS11': 'KOSPI',
        '^KQ11': 'KOSDAQ',
        '^GSPC': 'S&P 500',
        '^IXIC': 'Nasdaq'
    }
    if symbol in index_map:
        return symbol, index_map[symbol]
        
    display_name = get_us_stock_name(symbol)
    return symbol, display_name

def resolve_stock_selection(selected_display, krx_df):
    """
    선택된 '종목명 (코드/티커)' 문자열을 파싱하여 yfinance 티커와 표시 이름으로 변환합니다. (32 FinancialChart 방식)
    """
    if not selected_display or selected_display == "선택 안 함":
        return None, None

    if "(" in selected_display and selected_display.endswith(")"):
        code_part = selected_display.split("(")[-1].replace(")", "").strip()
        name_part = selected_display.split("(")[0].strip()

        # 한국 6자리 종목 코드인 경우
        if code_part.isdigit() and len(code_part) == 6:
            code_match = krx_df[krx_df['Code'] == code_part]
            if not code_match.empty:
                market = code_match.iloc[0]['Market']
                name = code_match.iloc[0]['Name']
                suffix = '.KS' if market == 'KOSPI' else '.KQ'
                return f"{code_part}{suffix}", name
            return f"{code_part}.KS", name_part
        else:
            # 미국 주식 티커
            symbol = code_part.upper()
            return symbol, name_part

    # 그 외 직접 입력된 텍스트 처리
    return resolve_ticker(selected_display, krx_df)

def format_price(value, ticker):
    """자산 종류에 맞게 화폐 단위 및 가격을 포맷팅합니다."""
    if ticker.startswith('^'):
        return f"{value:,.2f} pt"
    elif ticker.endswith('.KS') or ticker.endswith('.KQ'):
        return f"{int(round(value)):,} 원"
    else:
        return f"${value:,.2f}"

def format_return(value):
    """수익률 변동폭에 맞게 기호 및 색상을 적용한 텍스트를 반환합니다."""
    prefix = "+" if value > 0 else ""
    return f"{prefix}{value:.2f}%"

# --- UI 레이아웃 구성 ---

# KRX 데이터 로드
krx_df = load_krx_data()

# 종목 리스트 포맷팅 (32 FinancialChart 방식: 종목명 (코드))
if not krx_df.empty:
    krx_display_names = (krx_df['Name'] + " (" + krx_df['Code'] + ")").tolist()
else:
    krx_display_names = []

# 주요 미국 주식 목록 (한국어 종목명 + 티커)
us_stocks = [
    "애플 (AAPL)",
    "마이크로소프트 (MSFT)",
    "엔비디아 (NVDA)",
    "테슬라 (TSLA)",
    "아마존 (AMZN)",
    "알파벳A (GOOGL)",
    "메타 (META)",
    "버크셔해서웨이 (BRK-B)",
    "브로드컴 (AVGO)",
    "TSMC (TSM)",
    "일라이릴리 (LLY)",
    "JP모건 (JPM)",
    "월마트 (WMT)",
    "비자 (V)",
    "엑슨모빌 (XOM)",
    "넷플릭스 (NFLX)",
    "코스트코 (COST)",
    "ASML (ASML)",
    "AMD (AMD)",
    "퀄컴 (QCOM)",
    "팔란티어 (PLTR)",
    "아이온큐 (IONQ)",
    "인텔 (INTC)"
]

stock_select_options = ["선택 안 함"] + krx_display_names + us_stocks + ["[직접 입력]"]

# 종목 1 디폴트 인덱스 (삼성전자)
default_idx1 = 0
for idx, opt in enumerate(stock_select_options):
    if "삼성전자 (005930)" in opt:
        default_idx1 = idx
        break

# 종목 2 디폴트 인덱스 (엔비디아)
default_idx2 = 0
for idx, opt in enumerate(stock_select_options):
    if "엔비디아 (NVDA)" in opt:
        default_idx2 = idx
        break

# 사이드바 설정
st.sidebar.header("⚙️ 대시보드 설정")

st.sidebar.subheader("🔍 종목 선택 (최대 3개)")
stock_select1 = st.sidebar.selectbox(
    "종목 1",
    options=stock_select_options,
    index=default_idx1,
    help="키보드로 종목명(예: 삼성전자) 또는 종목코드(예: 005930)를 입력하여 검색할 수 있습니다."
)
custom_stock1 = None
if stock_select1 == "[직접 입력]":
    custom_stock1 = st.sidebar.text_input("종목 1 직접 입력 (코드/티커)", placeholder="예: AAPL, TSLA, 005930")

stock_select2 = st.sidebar.selectbox(
    "종목 2 (선택)",
    options=stock_select_options,
    index=default_idx2,
    help="키보드로 종목명 또는 종목코드를 입력하여 검색할 수 있습니다."
)
custom_stock2 = None
if stock_select2 == "[직접 입력]":
    custom_stock2 = st.sidebar.text_input("종목 2 직접 입력 (코드/티커)", placeholder="예: AAPL, TSLA, 005930")

stock_select3 = st.sidebar.selectbox(
    "종목 3 (선택)",
    options=stock_select_options,
    index=0,
    help="키보드로 종목명 또는 종목코드를 입력하여 검색할 수 있습니다."
)
custom_stock3 = None
if stock_select3 == "[직접 입력]":
    custom_stock3 = st.sidebar.text_input("종목 3 직접 입력 (코드/티커)", placeholder="예: AAPL, TSLA, 005930")

st.sidebar.subheader("📊 지수 선택 (최대 2개)")
indices_options = {
    "KOSPI": "^KS11",
    "KOSDAQ": "^KQ11",
    "S&P 500": "^GSPC",
    "Nasdaq": "^IXIC",
    "선택 안 함": None
}

index_select1 = st.sidebar.selectbox(
    "지수 선택 1",
    options=list(indices_options.keys()),
    index=0  # KOSPI 디폴트
)

index_select2 = st.sidebar.selectbox(
    "지수 선택 2",
    options=list(indices_options.keys()),
    index=2  # S&P 500 디폴트
)

st.sidebar.subheader("📅 기간 선택")
default_start = datetime.date(2026, 1, 1)
default_end = datetime.date.today()

start_date = st.sidebar.date_input("시작일", value=default_start)
end_date = st.sidebar.date_input("종료일", value=default_end)

if start_date > end_date:
    st.sidebar.error("시작일은 종료일보다 이전 날짜여야 합니다.")

# 조회 버튼
run_button = st.sidebar.button("조회하기 🚀", use_container_width=True)

# 메인 콘텐츠 실행 로직
# 첫 실행이거나 조회 버튼을 누른 경우 실행
if run_button or 'data_loaded' not in st.session_state:
    st.session_state['data_loaded'] = True
    
    # 1. 입력 종목 및 지수 리스트 정리
    targets = []
    
    # 종목 분석 (32 FinancialChart 선택 방식 처리)
    selected_items = [
        (stock_select1, custom_stock1),
        (stock_select2, custom_stock2),
        (stock_select3, custom_stock3)
    ]
    for i, (select_val, custom_val) in enumerate(selected_items):
        target_str = ""
        if select_val == "[직접 입력]":
            if custom_val and custom_val.strip():
                target_str = custom_val.strip()
        elif select_val and select_val != "선택 안 함":
            target_str = select_val

        if target_str:
            ticker, name = resolve_stock_selection(target_str, krx_df)
            if ticker:
                if not any(t[0] == ticker for t in targets):
                    targets.append((ticker, name, f"종목 {i+1}"))
            else:
                st.warning(f"종목 '{target_str}'을(를) 해석할 수 없어 제외했습니다.")

    # 지수 분석
    for i, index_select in enumerate([index_select1, index_select2]):
        ticker = indices_options.get(index_select)
        if ticker:
            # 중복 방지
            if not any(t[0] == ticker for t in targets):
                targets.append((ticker, index_select, f"지수 {i+1}"))

    # 비교 대상이 없는 경우 예외 처리
    if not targets:
        st.info("비교할 종목 또는 지수를 왼쪽 사이드바에서 선택하거나 입력한 뒤 [조회하기] 버튼을 눌러주세요.")
    else:
        # 데이터 수집
        data_dict = {}
        original_data_dict = {}
        
        with st.spinner("금융 데이터를 가져오는 중입니다..."):
            # yfinance는 end가 exclusive이므로 1일을 더해줍니다.
            yf_end_date = end_date + datetime.timedelta(days=1)
            
            for ticker, display_name, category in targets:
                try:
                    # Ticker.history를 사용하여 데이터 가져오기
                    t_obj = yf.Ticker(ticker)
                    df = t_obj.history(start=start_date, end=yf_end_date)
                    
                    if df.empty:
                        st.warning(f"⚠️ '{display_name}' ({ticker})의 가격 데이터가 선택한 기간에 존재하지 않습니다.")
                        continue
                    
                    # 시간대 정보 제거 및 일자 단위 정규화
                    df.index = df.index.tz_localize(None).normalize()
                    
                    # Close 값 사용
                    series = df['Close'].dropna()
                    
                    if series.empty:
                        st.warning(f"⚠️ '{display_name}' ({ticker})의 유효한 종가 데이터가 없습니다.")
                        continue
                        
                    # 데이터 저장
                    original_data_dict[display_name] = (series, ticker)
                    
                    # 시작일 기준 100% 정규화
                    start_price = series.iloc[0]
                    series_normalized = (series / start_price) * 100
                    data_dict[display_name] = series_normalized
                    
                except Exception as e:
                    st.error(f"❌ '{display_name}' ({ticker}) 데이터를 가져오는 도중 에러 발생: {e}")

        # 로드된 데이터가 하나라도 있는 경우 화면 표시
        if data_dict:
            col1, col2 = st.columns([3, 1])
            
            # --- 차트 그리기 (Plotly) ---
            fig = go.Figure()
            
            chart_colors = ['#38BDF8', '#F43F5E', '#10B981', '#FBBF24', '#A855F7', '#EC4899', '#6366F1']
            for i, (display_name, series_normalized) in enumerate(data_dict.items()):
                c = chart_colors[i % len(chart_colors)]
                fig.add_trace(go.Scatter(
                    x=series_normalized.index,
                    y=series_normalized.values,
                    mode='lines',
                    name=display_name,
                    line=dict(width=2.5, color=c),
                    hovertemplate='%{x|%Y-%m-%d}<br><b>' + display_name + '</b>: %{y:.2f}%<extra></extra>'
                ))
            
            # 32 FinancialChart 테마 적용 (슬레이트 다크 그레이 & 고대비 텍스트)
            fig.update_layout(
                title=dict(
                    text=f"<b>수익률 비교 차트 ({start_date} ~ {end_date}, 시작가 = 100%)</b>",
                    x=0.0,
                    font=dict(size=18, color="#F8FAFC")
                ),
                xaxis=dict(
                    title=dict(text="날짜", font=dict(color="#E2E8F0")),
                    gridcolor="#2A3342",
                    showline=True,
                    linewidth=1,
                    linecolor="#3E4C5E",
                    tickfont=dict(color="#E2E8F0")
                ),
                yaxis=dict(
                    title=dict(text="수익률 지수 (%)", font=dict(color="#E2E8F0")),
                    gridcolor="#2A3342",
                    showline=True,
                    linewidth=1,
                    linecolor="#3E4C5E",
                    ticksuffix="%",
                    tickfont=dict(color="#E2E8F0")
                ),
                hovermode="x unified",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                    font=dict(size=12, color="#E2E8F0"),
                    bgcolor="rgba(30, 36, 48, 0.9)",
                    bordercolor="#3E4C5E",
                    borderwidth=1
                ),
                hoverlabel=dict(
                    bgcolor="#0F172A",
                    font_color="#FFFFFF",
                    font_size=12,
                    bordercolor="#3E4C5E"
                ),
                font=dict(
                    family="Pretendard, Malgun Gothic, -apple-system, sans-serif",
                    color="#E2E8F0"
                ),
                plot_bgcolor="#161B24",   # 32 FinancialChart 딥 슬레이트 그레이 플롯 영역
                paper_bgcolor="#1E2430",  # 32 FinancialChart 엘레강트 슬레이트 다크 그레이 페이퍼 영역
                margin=dict(l=40, r=40, t=80, b=40),
                height=550
            )
            
            # 메인 화면 차트 출력 (theme=None을 설정하여 스트림릿 다크 모드 오버라이드를 방지하고 커스텀 테마를 그대로 유지)
            st.plotly_chart(fig, use_container_width=True, theme=None)
            
            # --- 요약 분석 표 생성 ---
            st.subheader("📊 비교 분석 요약 테이블")
            
            summary_rows = []
            for display_name, (series, ticker) in original_data_dict.items():
                start_val = series.iloc[0]
                end_val = series.iloc[-1]
                
                # 누적 수익률 계산
                total_return = ((end_val - start_val) / start_val) * 100
                
                # 기간 내 최고/최저가 및 그에 대응하는 누적수익률
                max_val = series.max()
                min_val = series.min()
                
                max_return = ((max_val - start_val) / start_val) * 100
                min_return = ((min_val - start_val) / start_val) * 100
                
                summary_rows.append({
                    "종목/지수명": display_name,
                    "티커": ticker,
                    "시작 가격": format_price(start_val, ticker),
                    "최종 가격": format_price(end_val, ticker),
                    "최종 수익률": total_return,
                    "기간 최고 수익률": max_return,
                    "기간 최저 수익률": min_return
                })
            
            summary_df = pd.DataFrame(summary_rows)
            
            # 스타일링 적용 및 출력
            # 누적 수익률 값을 보기 좋은 포맷의 텍스트로 변환
            styled_df = summary_df.copy()
            styled_df["최종 수익률"] = styled_df["최종 수익률"].apply(format_return)
            styled_df["기간 최고 수익률"] = styled_df["기간 최고 수익률"].apply(format_return)
            styled_df["기간 최저 수익률"] = styled_df["기간 최저 수익률"].apply(format_return)
            
            st.dataframe(
                styled_df,
                use_container_width=True,
                hide_index=True
            )
            
            # 간단한 성과 비교 인사이트 제공
            st.markdown("### 💡 주요 성과 인사이트")
            
            # 최고 수익률 자산 찾기
            best_asset = max(summary_rows, key=lambda x: x["최종 수익률"])
            worst_asset = min(summary_rows, key=lambda x: x["최종 수익률"])
            
            st.write(
                f"• 선택한 기간 동안 가장 높은 성과를 낸 자산은 **{best_asset['종목/지수명']}**이며, "
                f"최종 수익률은 **{format_return(best_asset['최종 수익률'])}**을 기록했습니다."
            )
            st.write(
                f"• 반면 가장 저조한 성과를 낸 자산은 **{worst_asset['종목/지수명']}**이며, "
                f"최종 수익률은 **{format_return(worst_asset['최종 수익률'])}**을 기록했습니다."
            )
            
        else:
            st.error("가져온 가격 데이터가 모두 비어 있어 차트를 생성하지 못했습니다. 입력 값 및 날짜 범위를 다시 확인해 주세요.")
