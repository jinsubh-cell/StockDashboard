// ==========================================
// Stock Data Module
// Mock data for Korean stock market
// ==========================================

// --- Market Indices ---
export const marketIndices = [
    {
        id: 'kospi',
        name: '코스피',
        nameEn: 'KOSPI',
        value: 2687.45,
        change: 32.18,
        changePercent: 1.21,
        history: generateHistory(2650, 40, 30)
    },
    {
        id: 'kosdaq',
        name: '코스닥',
        nameEn: 'KOSDAQ',
        value: 872.31,
        change: -5.67,
        changePercent: -0.65,
        history: generateHistory(870, 15, 30)
    },
    {
        id: 'kospi200',
        name: '코스피 200',
        nameEn: 'KOSPI 200',
        value: 358.92,
        change: 4.56,
        changePercent: 1.29,
        history: generateHistory(355, 8, 30)
    },
    {
        id: 'exchange',
        name: '원/달러 환율',
        nameEn: 'USD/KRW',
        value: 1342.50,
        change: -3.20,
        changePercent: -0.24,
        history: generateHistory(1340, 10, 30)
    }
];

// --- Stocks ---
export const stocks = [
    {
        code: '005930',
        name: '삼성전자',
        sector: '반도체',
        price: 78200,
        change: 1800,
        changePercent: 2.36,
        volume: 18234567,
        marketCap: '466.8조',
        per: 14.2,
        pbr: 1.35,
        high52w: 88800,
        low52w: 59000,
        open: 76800,
        high: 78500,
        low: 76200,
        prevClose: 76400,
        foreignRate: 52.3,
        description: '세계 최대 메모리 반도체 제조업체. DRAM, NAND Flash, 시스템 LSI, 파운드리 사업을 영위.',
        history: generateStockHistory(72000, 8000, 90)
    },
    {
        code: '000660',
        name: 'SK하이닉스',
        sector: '반도체',
        price: 185500,
        change: 5500,
        changePercent: 3.05,
        volume: 5432100,
        marketCap: '135.1조',
        per: 9.8,
        pbr: 2.15,
        high52w: 238000,
        low52w: 120000,
        open: 181000,
        high: 186000,
        low: 180500,
        prevClose: 180000,
        foreignRate: 48.7,
        description: 'HBM(고대역폭 메모리) 글로벌 시장 점유율 1위. AI 반도체 수혜주.',
        history: generateStockHistory(160000, 30000, 90)
    },
    {
        code: '035420',
        name: '네이버',
        sector: 'IT/플랫폼',
        price: 215000,
        change: -3000,
        changePercent: -1.38,
        volume: 1287654,
        marketCap: '35.1조',
        per: 22.5,
        pbr: 1.82,
        high52w: 242000,
        low52w: 170000,
        open: 218000,
        high: 219000,
        low: 214000,
        prevClose: 218000,
        foreignRate: 42.1,
        description: '국내 1위 포털 & 검색엔진. AI, 클라우드, 커머스, 웹툰/콘텐츠 등 사업 다각화.',
        history: generateStockHistory(200000, 25000, 90)
    },
    {
        code: '035720',
        name: '카카오',
        sector: 'IT/플랫폼',
        price: 42850,
        change: 750,
        changePercent: 1.78,
        volume: 3456789,
        marketCap: '19.0조',
        per: 35.2,
        pbr: 1.45,
        high52w: 55300,
        low52w: 33050,
        open: 42100,
        high: 43200,
        low: 41800,
        prevClose: 42100,
        foreignRate: 28.5,
        description: '국내 대표 메신저 카카오톡 운영. 모빌리티, 금융, 엔터테인먼트 등 다각화.',
        history: generateStockHistory(38000, 8000, 90)
    },
    {
        code: '051910',
        name: 'LG화학',
        sector: '화학/배터리',
        price: 312000,
        change: -8000,
        changePercent: -2.50,
        volume: 876543,
        marketCap: '22.0조',
        per: 18.9,
        pbr: 0.98,
        high52w: 420000,
        low52w: 280000,
        open: 320000,
        high: 321000,
        low: 310000,
        prevClose: 320000,
        foreignRate: 36.8,
        description: '국내 최대 화학기업. 배터리 자회사 LG에너지솔루션 보유.',
        history: generateStockHistory(340000, 40000, 90)
    },
    {
        code: '006400',
        name: '삼성SDI',
        sector: '배터리',
        price: 382000,
        change: 12000,
        changePercent: 3.24,
        volume: 654321,
        marketCap: '26.3조',
        per: 15.7,
        pbr: 1.28,
        high52w: 450000,
        low52w: 300000,
        open: 372000,
        high: 384000,
        low: 371000,
        prevClose: 370000,
        foreignRate: 41.2,
        description: '2차전지(리튬이온 배터리) 및 전자재료 전문 기업.',
        history: generateStockHistory(350000, 50000, 90)
    },
    {
        code: '373220',
        name: 'LG에너지솔루션',
        sector: '배터리',
        price: 368500,
        change: 8500,
        changePercent: 2.36,
        volume: 432100,
        marketCap: '86.2조',
        per: 42.3,
        pbr: 3.85,
        high52w: 450000,
        low52w: 320000,
        open: 362000,
        high: 370000,
        low: 360000,
        prevClose: 360000,
        foreignRate: 25.6,
        description: '글로벌 2차전지 TOP3. 파우치형 배터리 시장 점유율 1위.',
        history: generateStockHistory(350000, 40000, 90)
    },
    {
        code: '005380',
        name: '현대자동차',
        sector: '자동차',
        price: 242500,
        change: 3500,
        changePercent: 1.46,
        volume: 1234567,
        marketCap: '51.5조',
        per: 5.8,
        pbr: 0.65,
        high52w: 298000,
        low52w: 185000,
        open: 240000,
        high: 243000,
        low: 239000,
        prevClose: 239000,
        foreignRate: 33.4,
        description: '국내 최대 완성차 제조업체. 전기차, 수소차 등 미래차 전환 가속.',
        history: generateStockHistory(230000, 30000, 90)
    },
    {
        code: '000270',
        name: '기아',
        sector: '자동차',
        price: 118300,
        change: 2300,
        changePercent: 1.98,
        volume: 2345678,
        marketCap: '47.9조',
        per: 5.2,
        pbr: 0.92,
        high52w: 135000,
        low52w: 78000,
        open: 116500,
        high: 118800,
        low: 116000,
        prevClose: 116000,
        foreignRate: 37.1,
        description: '글로벌 완성차 기업. EV6, EV9 등 전기차 라인업으로 북미/유럽 시장 확대.',
        history: generateStockHistory(105000, 15000, 90)
    },
    {
        code: '055550',
        name: '신한지주',
        sector: '금융',
        price: 52800,
        change: 800,
        changePercent: 1.54,
        volume: 1876543,
        marketCap: '27.2조',
        per: 6.1,
        pbr: 0.52,
        high52w: 58000,
        low52w: 37000,
        open: 52200,
        high: 53000,
        low: 52000,
        prevClose: 52000,
        foreignRate: 61.5,
        description: '국내 대표 금융지주회사. 신한은행, 신한카드, 신한투자증권 등 보유.',
        history: generateStockHistory(48000, 6000, 90)
    },
    {
        code: '105560',
        name: 'KB금융',
        sector: '금융',
        price: 78900,
        change: 1200,
        changePercent: 1.54,
        volume: 1654321,
        marketCap: '32.4조',
        per: 6.5,
        pbr: 0.58,
        high52w: 86000,
        low52w: 52000,
        open: 78000,
        high: 79200,
        low: 77800,
        prevClose: 77700,
        foreignRate: 68.2,
        description: 'KB국민은행을 핵심 자회사로 보유한 금융지주회사.',
        history: generateStockHistory(72000, 8000, 90)
    },
    {
        code: '028260',
        name: '삼성물산',
        sector: '건설/지주',
        price: 137500,
        change: -1500,
        changePercent: -1.08,
        volume: 543210,
        marketCap: '25.8조',
        per: 11.2,
        pbr: 0.75,
        high52w: 165000,
        low52w: 110000,
        open: 139000,
        high: 139500,
        low: 137000,
        prevClose: 139000,
        foreignRate: 19.8,
        description: '건설, 상사, 패션, 리조트부문을 영위하는 삼성그룹 지주회사.',
        history: generateStockHistory(130000, 15000, 90)
    },
    {
        code: '012330',
        name: '현대모비스',
        sector: '자동차부품',
        price: 231000,
        change: 4000,
        changePercent: 1.76,
        volume: 432100,
        marketCap: '21.8조',
        per: 7.3,
        pbr: 0.55,
        high52w: 280000,
        low52w: 195000,
        open: 228000,
        high: 232000,
        low: 227000,
        prevClose: 227000,
        foreignRate: 39.6,
        description: '현대기아차 핵심 부품 공급업체. 자율주행, 전동화 부품 전문.',
        history: generateStockHistory(220000, 25000, 90)
    },
    {
        code: '068270',
        name: '셀트리온',
        sector: '바이오',
        price: 178500,
        change: -2500,
        changePercent: -1.38,
        volume: 987654,
        marketCap: '24.6조',
        per: 28.4,
        pbr: 3.25,
        high52w: 215000,
        low52w: 145000,
        open: 181000,
        high: 182000,
        low: 177000,
        prevClose: 181000,
        foreignRate: 15.3,
        description: '국내 대표 바이오의약품 기업. 바이오시밀러 글로벌 시장 선도.',
        history: generateStockHistory(170000, 20000, 90)
    },
    {
        code: '207940',
        name: '삼성바이오로직스',
        sector: '바이오',
        price: 812000,
        change: 22000,
        changePercent: 2.78,
        volume: 234567,
        marketCap: '54.0조',
        per: 55.3,
        pbr: 8.12,
        high52w: 950000,
        low52w: 680000,
        open: 795000,
        high: 815000,
        low: 792000,
        prevClose: 790000,
        foreignRate: 12.8,
        description: 'CMO(위탁생산) 글로벌 1위. 바이오의약품 생산능력 세계 최대.',
        history: generateStockHistory(780000, 80000, 90)
    },
    {
        code: '034730',
        name: 'SK이노베이션',
        sector: '에너지',
        price: 112500,
        change: -3500,
        changePercent: -3.02,
        volume: 1123456,
        marketCap: '10.6조',
        per: 8.7,
        pbr: 0.48,
        high52w: 145000,
        low52w: 95000,
        open: 116000,
        high: 116500,
        low: 112000,
        prevClose: 116000,
        foreignRate: 22.4,
        description: '석유화학, 윤활유, E&P사업. 배터리 자회사 SK온 보유.',
        history: generateStockHistory(120000, 15000, 90)
    },
    {
        code: '003670',
        name: '포스코퓨처엠',
        sector: '소재',
        price: 245000,
        change: 7000,
        changePercent: 2.94,
        volume: 765432,
        marketCap: '15.1조',
        per: 38.5,
        pbr: 4.21,
        high52w: 340000,
        low52w: 190000,
        open: 240000,
        high: 247000,
        low: 238000,
        prevClose: 238000,
        foreignRate: 18.9,
        description: '2차전지 양극재·음극재 제조. 포스코그룹 배터리 소재 핵심.',
        history: generateStockHistory(230000, 30000, 90)
    },
    {
        code: '066570',
        name: 'LG전자',
        sector: '전자/가전',
        price: 98700,
        change: 1700,
        changePercent: 1.75,
        volume: 1567890,
        marketCap: '16.1조',
        per: 10.2,
        pbr: 0.85,
        high52w: 115000,
        low52w: 78000,
        open: 97500,
        high: 99000,
        low: 97000,
        prevClose: 97000,
        foreignRate: 27.3,
        description: '글로벌 가전 브랜드. TV, 가전, 전장부품 등 사업 영위.',
        history: generateStockHistory(90000, 12000, 90)
    },
    {
        code: '003550',
        name: 'LG',
        sector: '지주',
        price: 75400,
        change: -400,
        changePercent: -0.53,
        volume: 234567,
        marketCap: '11.9조',
        per: 9.8,
        pbr: 0.62,
        high52w: 92000,
        low52w: 67000,
        open: 76000,
        high: 76200,
        low: 75200,
        prevClose: 75800,
        foreignRate: 31.5,
        description: 'LG그룹 지주회사. LG전자, LG화학, LG에너지솔루션 등 보유.',
        history: generateStockHistory(73000, 8000, 90)
    },
    {
        code: '247540',
        name: '에코프로비엠',
        sector: '2차전지소재',
        price: 168000,
        change: 8000,
        changePercent: 5.0,
        volume: 2345678,
        marketCap: '12.2조',
        per: 85.5,
        pbr: 12.3,
        high52w: 310000,
        low52w: 115000,
        open: 162000,
        high: 170000,
        low: 161000,
        prevClose: 160000,
        foreignRate: 8.7,
        description: '양극재 전문 제조업체. 하이니켈 양극재 기술력 보유.',
        history: generateStockHistory(150000, 30000, 90)
    }
];

// --- AI Recommendations ---
export const recommendations = [
    // KOSPI 20
    { code: '005930', market: 'KOSPI', signal: 'buy', targetPrice: 92000, confidence: 88, reason: '반도체 업황 회복 및 HBM3 공급 확대 기대.', factors: ['업황 회복', 'HBM 수혜', '저평가'] },
    { code: '000660', market: 'KOSPI', signal: 'buy', targetPrice: 220000, confidence: 92, reason: 'AI 서버 수요 가동으로 인한 메모리 수익성 개선.', factors: ['메모리 반등', 'AI 수혜', '실적 개선'] },
    { code: '207940', market: 'KOSPI', signal: 'buy', targetPrice: 920000, confidence: 85, reason: '고수익 수주 지속 및 글로벌 생산 능력 확대.', factors: ['바이오', '수주 성장', '실적 안정'] },
    { code: '373220', market: 'KOSPI', signal: 'hold', targetPrice: 480000, confidence: 70, reason: '전기차 업황 부진 영향이나 장기 경쟁력 유지.', factors: ['이차전지', '북미 시장', '변동성'] },
    { code: '005380', market: 'KOSPI', signal: 'buy', targetPrice: 300000, confidence: 82, reason: '고부가 가치 차종 판매 호조 및 주주환원 기대.', factors: ['자동차', '배당 매력', '실적 호조'] },
    { code: '000270', market: 'KOSPI', signal: 'buy', targetPrice: 145000, confidence: 85, reason: '수익성 위주의 경영 성과 및 저평가 매력.', factors: ['자동차', '고수익성', '밸류업'] },
    { code: '035420', market: 'KOSPI', signal: 'buy', targetPrice: 240000, confidence: 75, reason: 'AI 플랫폼 경쟁력 강화 및 수익 모델 다변화.', factors: ['IT', 'AI', '광고'] },
    { code: '006400', market: 'KOSPI', signal: 'buy', targetPrice: 550000, confidence: 78, reason: '전기차 및 에너지 저장 장치 수요 증가 수혜.', factors: ['배터리', '수익성 개선', '성장성'] },
    { code: '051910', market: 'KOSPI', signal: 'hold', targetPrice: 550000, confidence: 68, reason: '범용 화학 부문 부진하나 신성장 동력 확보.', factors: ['화학', '배터리 소재', '중장기'] },
    { code: '035720', market: 'KOSPI', signal: 'hold', targetPrice: 65000, confidence: 62, reason: '플랫폼 광고 매출 견조하나 계열사 리스크 관리 필요.', factors: ['IT', '메신저', '수익 개편'] },
    { code: '105560', market: 'KOSPI', signal: 'buy', targetPrice: 85000, confidence: 84, reason: '금리 환경 우호적이며 가계 및 기업 대출 견조.', factors: ['금융', '고배당', '주주환원'] },
    { code: '055550', market: 'KOSPI', signal: 'buy', targetPrice: 60000, confidence: 82, reason: '비은행 부문 기여도 증대 및 안정적 자산 건전성.', factors: ['금융', '은행', '배당 매력'] },
    { code: '028260', market: 'KOSPI', signal: 'buy', targetPrice: 180000, confidence: 77, reason: '건설 및 상사 부문 실적 개선 및 지배구조 매력.', factors: ['지주사', '건설', '삼성그룹'] },
    { code: '068270', market: 'KOSPI', signal: 'buy', targetPrice: 230000, confidence: 80, reason: '합병 효과 본격화 및 신약 바이오시밀러 출시.', factors: ['바이오', '합병', '연구개발'] },
    { code: '012330', market: 'KOSPI', signal: 'buy', targetPrice: 290000, confidence: 79, reason: '현대차그룹 생산 증가에 따른 모듈 및 핵심부품 성장.', factors: ['자동차 부품', '모빌리티', '안정적'] },
    { code: '003670', market: 'KOSPI', signal: 'buy', targetPrice: 350000, confidence: 74, reason: '양극재 출하량 증가 및 원가 경쟁력 확보.', factors: ['이차전지 소재', '포스코그룹', '성장'] },
    { code: '066570', market: 'KOSPI', signal: 'buy', targetPrice: 135000, confidence: 76, reason: '가전 부문 프리미엄 전략 및 전장 사업 흑자 지속.', factors: ['가전', '전장', '실적 반등'] },
    { code: '247540', market: 'KOSPI', signal: 'buy', targetPrice: 220000, confidence: 88, reason: '양극재 생산 능력 증대 및 고객사 다변화.', factors: ['이차전지 소재', '코스닥 대장', '성장'] },
    { code: '034730', market: 'KOSPI', signal: 'hold', targetPrice: 145000, confidence: 65, reason: '정유 부문 변동성 있으나 신규 사업 가치 가시화.', factors: ['정유', '에너지', '턴어라운드'] },
    { code: '005490', market: 'KOSPI', signal: 'buy', targetPrice: 550000, confidence: 73, reason: '철강 시황 회복 지연이나 리튬 사업 성장성 유효.', factors: ['철강', '리튬', '원자재'] },

    // KOSDAQ 20
    { code: '086520', name: '에코프로', market: 'KOSDAQ', sector: '이차전지', price: 98500, changePct: 3.15, signal: 'buy', targetPrice: 120000, confidence: 85, reason: '지주사 가치 재평가 및 이차전지 생태계 핵심.', factors: ['지주사', '이차전지', '성장'] },
    { code: '091990', name: '셀트리온헬스케어', market: 'KOSDAQ', sector: '바이오', price: 72300, changePct: 1.82, signal: 'buy', targetPrice: 95000, confidence: 82, reason: '면역항암제 신약 가치 및 글로벌 임상 진척.', factors: ['신약', '바이오', '임상'] },
    { code: '247540', name: '에코프로비엠', market: 'KOSDAQ', sector: '양극재', price: 168000, changePct: 5.00, signal: 'buy', targetPrice: 220000, confidence: 88, reason: '코스닥 대장주로서의 상징성 및 양극재 성장성.', factors: ['대본주', '양극재', '성장'] },
    { code: '066970', name: 'JYP Ent.', market: 'KOSDAQ', sector: '엔터', price: 52800, changePct: 2.33, signal: 'buy', targetPrice: 65000, confidence: 80, reason: '글로벌 엔터 시장 영향력 확대 및 신인 그룹 데뷔.', factors: ['엔터', 'K-POP', '콘텐츠'] },
    { code: '035900', name: 'JW중외제약', market: 'KOSDAQ', sector: '제약', price: 58400, changePct: 1.56, signal: 'buy', targetPrice: 75000, confidence: 78, reason: '진단 키트 포트폴리오 다변화 및 해외 거점 확대.', factors: ['진단', '의료기기', '수출'] },
    { code: '214150', name: '클래시스', market: 'KOSDAQ', sector: '의료기기', price: 28900, changePct: -0.69, signal: 'hold', targetPrice: 35000, confidence: 65, reason: '바이오 시밀러 시장 경쟁 심화 및 신약 파이프라인.', factors: ['시밀러', '박행성', '연구개발'] },
    { code: '293480', name: '카카오게임즈', market: 'KOSDAQ', sector: '게임', price: 35200, changePct: 2.92, signal: 'buy', targetPrice: 45000, confidence: 75, reason: '신작 게임 흥행 기대 및 미디어 플랫폼 성장.', factors: ['게임', '플랫폼', '콘텐츠'] },
    { code: '112040', name: '위메이드', market: 'KOSDAQ', sector: '게임', price: 11500, changePct: 1.77, signal: 'buy', targetPrice: 15000, confidence: 82, reason: '첨단 산업용 가스 수요 증가 및 실적 안정성.', factors: ['소재', '반도체 가스', '실적'] },
    { code: '036930', name: '주성엔지니어링', market: 'KOSDAQ', sector: '반도체장비', price: 14200, changePct: 3.65, signal: 'buy', targetPrice: 18000, confidence: 76, reason: '북미 전력 인프라 투자 확대 수혜 및 실적 개선.', factors: ['전력 기기', '수출', '인프라'] },
    { code: '025980', name: '아난티', market: 'KOSDAQ', sector: '레저', price: 68500, changePct: 1.48, signal: 'buy', targetPrice: 85000, confidence: 84, reason: '게임 흥행 지속 및 모바일 퍼블리싱 강화.', factors: ['게임', '글로벌', '캐시카우'] },
    { code: '145020', name: '휴젤', market: 'KOSDAQ', sector: '바이오', price: 178000, changePct: 2.30, signal: 'buy', targetPrice: 220000, confidence: 85, reason: '보툴리눔 톡신 글로벌 승인 가속 및 소송 리스크 완화.', factors: ['바이오', '수출', '수익성'] },
    { code: '078600', name: '대주전자재료', market: 'KOSDAQ', sector: '소재', price: 33500, changePct: 1.52, signal: 'buy', targetPrice: 42000, confidence: 80, reason: '신작 라인업 강화 및 글로벌 IP 파워 증명.', factors: ['엔터', '음반', '굿즈'] },
    { code: '039030', name: '이오테크닉스', market: 'KOSDAQ', sector: '반도체장비', price: 21800, changePct: 2.83, signal: 'buy', targetPrice: 28000, confidence: 77, reason: '반도체 소재 공급 정상화 및 고객사 다변화.', factors: ['소재', '반도체', '국산화'] },
    { code: '067310', name: '하나마이크론', market: 'KOSDAQ', sector: '반도체', price: 9850, changePct: -1.20, signal: 'hold', targetPrice: 12000, confidence: 68, reason: '수주 잔고 풍부하나 원가 부담 지속 우려.', factors: ['기계', '수주', '실적'] },
    { code: '048410', name: '현대바이오사이언스', market: 'KOSDAQ', sector: '바이오', price: 11200, changePct: 2.19, signal: 'buy', targetPrice: 15000, confidence: 75, reason: '스마트 시티 및 국방 솔루션 수주 확대.', factors: ['통신', '방산', 'SI'] },
    { code: '067160', name: '아프리카TV', market: 'KOSDAQ', sector: '미디어', price: 108500, changePct: 1.40, signal: 'buy', targetPrice: 140000, confidence: 82, reason: '반도체 후공정 장비 수요 급증 및 기술 우위.', factors: ['장비', 'HBM', '기술'] },
    { code: '036830', name: '솔브레인홀딩스', market: 'KOSDAQ', sector: '소재', price: 38200, changePct: 2.14, signal: 'buy', targetPrice: 48000, confidence: 79, reason: '테스트 핸들러 글로벌 점유율 1위 및 실적 성장.', factors: ['반도체', '장비', '수출'] },
    { code: '086450', name: '동국제약', market: 'KOSDAQ', sector: '제약', price: 27600, changePct: 1.10, signal: 'buy', targetPrice: 35000, confidence: 76, reason: '비대면 진료 및 디지털 헬스케어 정책 수혜.', factors: ['의료IT', '플랫폼', '정책'] },
    { code: '012450', name: '한화에어로스페이스', market: 'KOSDAQ', sector: '방산', price: 43200, changePct: 3.10, signal: 'buy', targetPrice: 55000, confidence: 80, reason: '자율주행 핵심 모듈 공급 및 ADAS 채택 확대.', factors: ['자율주행', '전장', '성장'] },
    { code: '053800', name: '안랩', market: 'KOSDAQ', sector: '보안', price: 9200, changePct: 0.88, signal: 'buy', targetPrice: 12000, confidence: 74, reason: '온라인 결제 시장 성장 및 핀테크 경쟁력 강화.', factors: ['결제', '핀테크', '안정성'] }
];

// --- Sector Performance ---
export const sectorPerformance = [
    { name: '반도체', change: 2.85, color: '#6c5ce7' },
    { name: '2차전지', change: 3.12, color: '#00cec9' },
    { name: '자동차', change: 1.65, color: '#0984e3' },
    { name: '바이오', change: 0.45, color: '#e17055' },
    { name: '금융', change: 1.42, color: '#fdcb6e' },
    { name: 'IT/플랫폼', change: -0.38, color: '#d63031' },
    { name: '화학', change: -1.82, color: '#636e72' },
    { name: '에너지', change: -2.15, color: '#2d3436' }
];

// --- Helper Functions ---
function generateHistory(base, range, days) {
    days = 1825; // Overridden to 5 years for timeframes
    const data = [];
    let val = base;
    for (let i = 0; i < days; i++) {
        val += (Math.random() - 0.48) * (range / 5);
        val = Math.max(base - range, Math.min(base + range, val));
        data.push(parseFloat(val.toFixed(2)));
    }
    return data;
}

function generateStockHistory(base, range, days) {
    days = 1825; // Overridden to 5 years for timeframes
    const data = [];
    let val = base;
    for (let i = 0; i < days; i++) {
        val += (Math.random() - 0.47) * (range / 8);
        val = Math.max(base - range * 0.5, Math.min(base + range * 0.8, val));
        data.push(Math.round(val));
    }
    return data;
}

function generateStockOHLCHistory(historyData, days) {
    const ohlc = [];
    const now = new Date();
    now.setHours(0, 0, 0, 0);

    for (let i = 0; i < historyData.length; i++) {
        const c = historyData[i];
        let prevC = i > 0 ? historyData[i - 1] : c;
        let o = prevC + (c - prevC) * Math.random();
        let h = Math.max(o, c) + Math.abs((c - prevC)) * Math.random() * 2;
        let l = Math.min(o, c) - Math.abs((c - prevC)) * Math.random() * 2;

        const d = new Date(now);
        // historyData length is `days`, index 0 is `days - 1` days ago
        d.setDate(d.getDate() - (historyData.length - 1 - i));

        ohlc.push({
            x: d.valueOf(),
            o: Math.round(o),
            h: Math.round(h),
            l: Math.round(l),
            c: Math.round(c)
        });
    }
    return ohlc;
}

// Attach ohlcHistory to each stock
stocks.forEach(s => {
    s.ohlcHistory = generateStockOHLCHistory(s.history, s.history.length);
});

export function getStockByCode(code) {
    return stocks.find(s => s.code === code);
}

// Ensure a stock entry has all detail fields populated (creates if missing)
export function getOrCreateStock(code, name, price) {
    let stock = stocks.find(s => s.code === code);
    const p = stock?.price || price || 50000;
    if (!stock) {
        stock = { code, name: name || code, sector: '-', price: p, change: 0, changePercent: 0, volume: 0, marketCap: '-' };
        stocks.push(stock);
    }
    // Fill missing detail fields based on current price
    if (!stock.ohlcHistory || stock.ohlcHistory.length === 0) {
        const range = Math.round(p * 0.3);
        stock.history = generateStockHistory(p, range, 90);
        stock.ohlcHistory = generateStockOHLCHistory(stock.history, stock.history.length);
    }
    if (!stock.open) stock.open = Math.round(p * (1 + (Math.random() - 0.5) * 0.02));
    if (!stock.high) stock.high = Math.round(p * (1 + Math.random() * 0.03));
    if (!stock.low) stock.low = Math.round(p * (1 - Math.random() * 0.03));
    if (!stock.prevClose) stock.prevClose = p - (stock.change || 0);
    if (!stock.high52w) stock.high52w = Math.round(p * 1.3);
    if (!stock.low52w) stock.low52w = Math.round(p * 0.7);
    if (stock.foreignRate === undefined) stock.foreignRate = +(Math.random() * 30 + 5).toFixed(1);
    if (!stock.per) stock.per = '-';
    if (!stock.pbr) stock.pbr = '-';
    if (!stock.description) stock.description = '';
    return stock;
}

export function getRecommendationByCode(code) {
    return recommendations.find(r => r.code === code) || null;
}

export function searchStocks(query) {
    const q = query.toLowerCase();
    return stocks.filter(s =>
        s.name.toLowerCase().includes(q) ||
        s.code.includes(q) ||
        s.sector.toLowerCase().includes(q)
    ).slice(0, 8);
}

export function getTopByVolume(count = 10) {
    return [...stocks].sort((a, b) => b.volume - a.volume).slice(0, count);
}

export function getTopGainers(count = 5) {
    return [...stocks].sort((a, b) => b.changePercent - a.changePercent).slice(0, count);
}

export function getTopLosers(count = 5) {
    return [...stocks].sort((a, b) => a.changePercent - b.changePercent).slice(0, count);
}

export function formatPrice(price) {
    return price.toLocaleString('ko-KR');
}

export function formatVolume(vol) {
    if (vol >= 100000000) return (vol / 100000000).toFixed(1) + '억';
    if (vol >= 10000) return (vol / 10000).toFixed(0) + '만';
    return vol.toLocaleString();
}

export function generateDates(days) {
    const dates = [];
    const now = new Date();
    for (let i = days - 1; i >= 0; i--) {
        const d = new Date(now);
        d.setDate(d.getDate() - i);
        dates.push(`${d.getMonth() + 1}/${d.getDate()}`);
    }
    return dates;
}
