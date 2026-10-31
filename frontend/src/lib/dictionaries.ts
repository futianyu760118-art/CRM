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

export const LEAD_LEVEL_OPTIONS = toOptions(LEAD_LEVELS);
export const LEAD_CHANNEL_OPTIONS = toOptions(LEAD_CHANNELS);
export const CUSTOMER_SOURCE_OPTIONS = toOptions(CUSTOMER_SOURCES);
export const CUSTOMER_TYPE_OPTIONS = toOptions(CUSTOMER_TYPES);
export const PAYMENT_METHOD_OPTIONS = toOptions(PAYMENT_METHODS);
export const CONTACT_RELATION_OPTIONS = toOptions(CONTACT_RELATION_TYPES);

export function labelOf(dict: Record<string, string>, value?: string | null): string {
  if (!value) return '-';
  return dict[value] ?? value;
}
