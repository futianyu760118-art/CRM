/**
 * 客户域枚举字典（与后端 app/domain/dictionaries.py 保持一致，PAND-312 D1）。
 */

export type Option = { value: string; label: string };

function toOptions(dict: Record<string, string>): Option[] {
  return Object.entries(dict).map(([value, label]) => ({ value, label }));
}

export const LEAD_LEVELS: Record<string, string> = {
  A: 'A级（高意向）',
  B: 'B级（中意向）',
  C: 'C级（低意向）',
};

export const LEAD_CHANNELS: Record<string, string> = {
  EXHIBITION: '展会',
  B2B: 'B2B平台',
  WEBSITE: '官网询盘',
  REFERRAL: '客户推荐',
  DIRECT: '自主开发',
  AGENT: '代理商',
  SOCIAL: '社媒',
  OTHER: '其他',
};

export const CUSTOMER_SOURCES: Record<string, string> = {
  EXHIBITION: '展会',
  YUNQUTONG: '云渠通',
  WEBSITE: '官网',
  DIRECT: '主动开发',
  B2B: 'B2B平台',
  REFERRAL: '客户推荐',
  AGENT: '代理商',
  SOCIAL: '社媒',
  OTHER: '其他',
};

export const CUSTOMER_TYPES: Record<string, string> = {
  END_USER: '终端用户',
  TRADER: '贸易商',
  AGENT: '代理商',
  DISTRIBUTOR: '分销商',
  FACTORY: '生产工厂',
  OTHER: '其他',
};

export const PAYMENT_METHODS: Record<string, string> = {
  TT: 'T/T 电汇',
  LC: 'L/C 信用证',
  DP: 'D/P 付款交单',
  DA: 'D/A 承兑交单',
  OA: 'O/A 赊销',
  WU: '西联汇款',
  CASH: '现金',
  OTHER: '其他',
};

export const CONTACT_RELATION_TYPES: Record<string, string> = {
  DECISION_MAKER: '决策人',
  PURCHASING: '采购对接人',
  TECHNICAL: '技术对接人',
  FINANCE: '财务对接人',
  LOGISTICS: '物流对接人',
  OTHER: '其他',
};

export const CUSTOMER_GROUPS: Record<string, string> = {
  new: '新客户',
  active: '活跃客户',
  dormant: '休眠客户',
};

// PAND-316：产品资料 / 标准报价 / 样品（与后端字典一致）
export const PRODUCT_DOC_TYPES: Record<string, string> = {
  SALES_MATERIAL: '销售资料',
  SPEC_SHEET: '规格书',
  TEST_REPORT: '测试报告',
  CERTIFICATION: '认证文件',
};

export const CURRENCIES: Record<string, string> = {
  USD: '美元',
  CNY: '人民币',
  EUR: '欧元',
  JPY: '日元',
  GBP: '英镑',
};

export const COURIERS: Record<string, string> = {
  SF: '顺丰',
  JD: '京东物流',
  ZTO: '中通',
  YTO: '圆通',
  YUNDA: '韵达',
  STO: '申通',
  EMS: 'EMS',
  DHL: 'DHL',
  FEDEX: 'FedEx',
  UPS: 'UPS',
  OTHER: '其他',
};

export const SAMPLE_STATUS_LABELS: Record<string, string> = {
  pending: '待确认',
  producing: '制作中',
  testing: '测试中',
  sent: '已寄出',
  feedback: '客户反馈',
};

/** 5 态只能逐级前进：当前状态 → 下一状态 */
export const SAMPLE_NEXT_STATUS: Record<string, string | undefined> = {
  pending: 'producing',
  producing: 'testing',
  testing: 'sent',
  sent: 'feedback',
  feedback: undefined,
};

export const QUOTE_STATUS_LABELS: Record<string, string> = {
  ACTIVE: '生效中',
  EXPIRED: '已过期',
  PENDING: '未生效',
  DISABLED: '已停用',
};

export const LEAD_LEVEL_OPTIONS = toOptions(LEAD_LEVELS);
export const LEAD_CHANNEL_OPTIONS = toOptions(LEAD_CHANNELS);
export const CUSTOMER_SOURCE_OPTIONS = toOptions(CUSTOMER_SOURCES);
export const CUSTOMER_TYPE_OPTIONS = toOptions(CUSTOMER_TYPES);
export const PAYMENT_METHOD_OPTIONS = toOptions(PAYMENT_METHODS);
export const CONTACT_RELATION_OPTIONS = toOptions(CONTACT_RELATION_TYPES);
export const PRODUCT_DOC_TYPE_OPTIONS = toOptions(PRODUCT_DOC_TYPES);
export const CURRENCY_OPTIONS = toOptions(CURRENCIES);
export const COURIER_OPTIONS = toOptions(COURIERS);
export const SAMPLE_STATUS_OPTIONS = toOptions(SAMPLE_STATUS_LABELS);

export function labelOf(dict: Record<string, string>, value?: string | null): string {
  if (!value) return '-';
  return dict[value] ?? value;
}
