// 销售中心 6 模块类型（PAND-249：订单 / 样品 / 报价库 / 问题反馈）。

export interface SalesOrder {
  id: string;
  order_no: string;
  line_no: string;
  external_id: string | null;
  company_id: string | null;
  customer_name: string | null;
  customer_code: string | null;
  product_code: string | null;
  product_name: string | null;
  project_no: string | null;
  quantity: number;
  completed_qty: number;
  order_amount: number;
  status: string;
  risk_level: string;
  promised_date: string | null;
  plan_date: string | null;
  online_date: string | null;
  user_status_locked: boolean;
  remark: string | null;
  sync_status: string;
  last_sync_at: string | null;
  owner_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface OrderStats {
  by_status: Record<string, number>;
  by_risk: Record<string, number>;
}

export interface Sample {
  id: string;
  sample_no: string;
  external_id: string | null;
  company_id: string | null;
  customer_name: string;
  inquiry_no: string | null;
  inquiry_id: string | null;
  product_name: string | null;
  product_code: string | null;
  quantity: number;
  sample_type: string;
  status: string;
  send_date: string | null;
  confirm_date: string | null;
  remark: string | null;
  sync_status: string;
  last_sync_at: string | null;
  owner_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface SampleStats {
  by_status: Record<string, number>;
}

export interface QuoteLibrary {
  id: string;
  external_model: string;
  certificate_level: string;
  external_id: string | null;
  internal_model: string | null;
  product_name: string | null;
  category: string | null;
  power: string | null;
  configuration: string | null;
  specs: string | null;
  price_rmb: number | null;
  price_usd: number | null;
  unit_price: number | null;
  min_price: number | null;
  validity_days: number;
  usage_count: number;
  source_inquiry_no: string | null;
  remark: string | null;
  creator: string | null;
  sync_status: string;
  last_sync_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface QuoteStats {
  by_certificate_level: Record<string, number>;
  by_category: Record<string, number>;
}

export interface FeedbackFollowup {
  id: string;
  feedback_id: string;
  action: string;
  content: string | null;
  status_from: string | null;
  status_to: string | null;
  assignee: string | null;
  operator: string | null;
  operator_id: string | null;
  created_at: string;
}

export interface Feedback {
  id: string;
  feedback_no: string;
  external_id: string | null;
  title: string;
  description: string | null;
  type: string;
  priority: string;
  module: string | null;
  submitter: string | null;
  submitter_id: string | null;
  assignee: string | null;
  assignee_id: string | null;
  screenshots: string[] | null;
  source: string;
  status: string;
  resolution: string | null;
  resolved_at: string | null;
  sync_status: string;
  last_sync_at: string | null;
  followups: FeedbackFollowup[];
  followup_count: number;
  last_followup_at: string | null;
  last_followup_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface FeedbackStats {
  by_type: Record<string, number>;
  by_priority: Record<string, number>;
  by_status: Record<string, number>;
}
