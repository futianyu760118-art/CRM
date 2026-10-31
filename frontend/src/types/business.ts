export interface Lead {
  id: string;
  lead_no: string;
  name: string;
  contact_name: string | null;
  email: string | null;
  phone: string | null;
  country: string | null;
  industry: string | null;
  source: string;
  status: string;
  owner_id: string | null;
  assigned_at: string | null;
  converted_company_id: string | null;
  converted_at: string | null;
  remark: string | null;
  created_at: string;
}

export interface Company {
  id: string;
  code: string;
  name: string;
  name_en: string | null;
  country: string | null;
  currency: string;
  industry: string | null;
  customer_level: string | null;
  source: string | null;
  status: string;
  website: string | null;
  address: string | null;
  remark: string | null;
  external_id: string | null;
  sync_status: string | null;
  owner_id: string | null;
  owner_name?: string | null;
  owner_seq: number | null;
  global_seq: number | null;
  code_rule?: string | null;
  created_at: string;
  contact_count?: number;
}

export interface BusinessCodeItem {
  id: string;
  code: string;
  code_type: string;
  currency: string | null;
  is_primary: boolean;
}

export interface CurrencyCodeResult {
  id: string;
  code: string;
  currency: string | null;
  created: boolean;
}

export interface CustomerCodePreview {
  code: string;
  owner_code: string | null;
  owner_seq: number;
  global_seq: number;
  rule: string;
}

export interface CompanyDetail extends Company {
  business_codes: BusinessCodeItem[];
  contacts: {
    id: string;
    name: string;
    position: string | null;
    email: string | null;
    phone: string | null;
    mobile: string | null;
    is_primary: boolean;
  }[];
  opportunities: {
    id: string;
    opportunity_no: string;
    name: string;
    stage: string;
    estimated_amount: number | null;
    currency: string;
  }[];
  inquiries: {
    id: string;
    inquiry_no: string;
    status: string;
    currency: string;
    created_at: string | null;
  }[];
  email_threads: {
    id: string;
    subject: string | null;
    message_count: number;
    last_message_at: string | null;
  }[];
}

export interface Contact {
  id: string;
  company_id: string | null;
  company_name: string | null;
  name: string;
  position: string | null;
  email: string | null;
  phone: string | null;
  mobile: string | null;
  wechat: string | null;
  is_primary: boolean;
  remark: string | null;
  created_at: string;
}

export interface Opportunity {
  id: string;
  opportunity_no: string;
  name: string;
  company_id: string;
  company_name: string | null;
  primary_contact_id: string | null;
  stage: string;
  stage_label: string | null;
  estimated_amount: number | null;
  won_amount: number | null;
  currency: string;
  expected_close_date: string | null;
  probability: number | null;
  product_category: string | null;
  quantity: number | null;
  requirement: string | null;
  competitor: string | null;
  next_action: string | null;
  last_followup_at: string | null;
  lost_reason: string | null;
  inquiry_id: string | null;
  quotation_amount: number | null;
  status: string;
  owner_id: string | null;
  created_at: string;
}

export interface StageCatalog {
  value: string;
  label: string;
  next_stages: string[];
  required_fields: string[];
  roles: string[];
}

export interface KanbanColumn {
  stage: string;
  label: string;
  count: number;
  amount: number;
  cards: {
    id: string;
    opportunity_no: string;
    name: string;
    company_name: string | null;
    estimated_amount: number;
    currency: string;
    owner_id: string | null;
    probability: number | null;
  }[];
}

export interface Sku {
  id: string;
  product_id: string;
  code: string;
  spec: string | null;
  unit: string;
  price: number | null;
  cost: number | null;
  currency: string;
  status: string;
}

export interface Product {
  id: string;
  code: string;
  name: string;
  name_en: string | null;
  category: string | null;
  unit: string;
  description: string | null;
  status: string;
  created_at: string;
  skus: Sku[];
}

export interface InquiryItem {
  id?: string;
  product_id: string | null;
  sku_id: string | null;
  product_name: string;
  spec: string | null;
  quantity: number;
  unit: string;
  target_price: number | null;
  remark: string | null;
  sort?: number;
  group_type?: string;
  image_file_id?: string | null;
  product_model?: string | null;
  power?: string | null;
  voltage?: string | null;
  battery?: string | null;
  color_temp?: string | null;
  lumen?: string | null;
  light_source?: string | null;
  size?: string | null;
  cri?: string | null;
  led_count?: string | null;
  feature?: string | null;
  plug?: string | null;
  main_body?: string | null;
  lamp_shade?: string | null;
  reflector?: string | null;
  frame?: string | null;
  cable?: string | null;
  switch?: string | null;
  usb?: string | null;
  waterproof?: string | null;
  sensor?: string | null;
  certification?: string | null;
  quote_price?: number | null;
  quote_lead_time?: string | null;
  other_requirement?: string | null;
  other_requirement2?: string | null;
}

export interface Inquiry {
  id: string;
  inquiry_no: string;
  company_id: string | null;
  company_name: string | null;
  contact_id: string | null;
  contact_name: string | null;
  opportunity_id: string | null;
  source: string;
  requirement_text: string | null;
  currency: string;
  target_price: number | null;
  delivery_date: string | null;
  trade_terms: string | null;
  payment_terms: string | null;
  status: string;
  owner_id: string | null;
  owner_name: string | null;
  department_name: string | null;
  created_at: string;
  // 单据头
  customer_code: string | null;
  customer_name: string | null;
  customer_type: string | null;
  market: string | null;
  start_date: string | null;
  end_date: string | null;
  sample_date: string | null;
  order_date: string | null;
  shipment_date: string | null;
  first_order_amount: number | null;
  quantity_total: number | null;
  annual_amount: number | null;
  sample_lead_time: string | null;
  version_no: string | null;
  owner_name_text: string | null;
  department_name_text: string | null;
  spec_rows: { label: string; values: string[] }[] | null;
  items?: InquiryItem[];
  pricing_versions?: number;
}

export interface Pricing {
  id: string;
  inquiry_id: string;
  inquiry_no: string | null;
  company_name: string | null;
  version: number;
  status: string;
  currency: string;
  material_cost: number | null;
  labor_cost: number | null;
  packaging_cost: number | null;
  freight_cost: number | null;
  tooling_cost: number | null;
  customization_cost: number | null;
  moq_cost: number | null;
  other_cost: number | null;
  loss_cost: number | null;
  total_cost: number | null;
  base_cost: number | null;
  target_margin: number | null;
  discount_rate: number | null;
  floor_price: number | null;
  suggested_price: number | null;
  final_price: number | null;
  can_view_cost?: boolean;
  can_view_floor?: boolean;
  remark: string | null;
  approved_at: string | null;
  created_at: string;
}

export interface PricingRule {
  id: string;
  code: string;
  name: string;
  conditions: Record<string, unknown> | null;
  actions: Record<string, unknown> | null;
  priority: number;
  enabled: boolean;
  description: string | null;
  created_at: string;
}

export interface QuotationItem {
  id?: string;
  product_id: string | null;
  sku_id: string | null;
  product_name: string;
  spec: string | null;
  quantity: number;
  unit: string;
  unit_price: number;
  amount?: number;
  remark: string | null;
  sort?: number;
  item_no?: string | null;
  image_file_id?: string | null;
  description?: string | null;
  moq?: string | null;
  power?: string | null;
  ip?: string | null;
  lumen?: string | null;
  color_temp?: string | null;
  color_rendering?: string | null;
  price_valid?: string | null;
}

export interface Quotation {
  id: string;
  quotation_no: string;
  company_id: string;
  company_name: string | null;
  contact_id: string | null;
  contact_name: string | null;
  opportunity_id: string | null;
  inquiry_id: string | null;
  pricing_id: string | null;
  version: number;
  currency: string;
  exchange_rate: number;
  discount_rate: number | null;
  incoterm: string | null;
  payment_terms: string | null;
  warranty: string | null;
  valid_days: number;
  valid_until: string | null;
  subtotal: number | null;
  additional_fee: number | null;
  discount: number | null;
  tax_amount: number | null;
  total_amount: number | null;
  status: string;
  pdf_file_id: string | null;
  approval_id: string | null;
  remark: string | null;
  title: string | null;
  buyer_attn: string | null;
  seller_name: string | null;
  seller_address: string | null;
  seller_contact: string | null;
  terms: string[] | null;
  notes_cn: string | null;
  notes_en: string | null;
  approved_at: string | null;
  sent_at: string | null;
  created_at: string;
  items?: QuotationItem[];
}

export interface UploadedFile {
  id: string;
  name: string;
  mime: string | null;
  size: number;
  url: string;
}

export interface ApprovalTask {
  id: string;
  step: number;
  approver_role: string | null;
  approver_id: string | null;
  status: string;
  comment: string | null;
  acted_at: string | null;
}

export interface Approval {
  id: string;
  biz_type: string;
  biz_id: string;
  biz_no: string | null;
  title: string;
  status: string;
  current_step: number;
  total_steps: number;
  applicant_id: string | null;
  applicant_name: string | null;
  amount: number | null;
  discount_rate: number | null;
  currency: string;
  finished_at: string | null;
  created_at: string;
  tasks: ApprovalTask[];
  logs?: { action: string; operator_name: string | null; comment: string | null; created_at: string | null }[];
}

export interface EmailAccount {
  id: string;
  name: string;
  email: string;
  display_name: string | null;
  smtp_host: string | null;
  smtp_port: number;
  smtp_user: string | null;
  smtp_ssl: boolean;
  imap_host: string | null;
  imap_port: number;
  imap_user: string | null;
  imap_ssl: boolean;
  imap_folder: string;
  is_default: boolean;
  status: string;
  last_sync_at: string | null;
  created_at: string;
  simulated?: boolean;
}

export interface EmailAttachment {
  id: string;
  filename: string;
  size: number;
  mime: string | null;
  file_id: string | null;
}

export interface EmailMessage {
  id: string;
  thread_id: string | null;
  account_id: string | null;
  direction: string;
  from_addr: string | null;
  from_name: string | null;
  to_addrs: string | null;
  cc_addrs: string | null;
  subject: string | null;
  body_text: string | null;
  sent_at: string | null;
  received_at: string | null;
  is_read: boolean;
  has_attachment: boolean;
  matched_by: string | null;
  send_status: string | null;
  error_message: string | null;
  created_at: string;
  company_id?: string | null;
  company_name?: string | null;
  opportunity_id?: string | null;
  attachments?: EmailAttachment[];
}

export interface IntegrationLog {
  id: string;
  system: string;
  action: string;
  request_id: string | null;
  idempotency_key: string | null;
  business_id: string | null;
  status: string;
  retry_count: number;
  max_retry: number;
  next_retry_at: string | null;
  error_message: string | null;
  created_at: string;
}

export interface SyncResult {
  batch_id: string;
  total: number;
  success: number;
  failed: number;
  skipped: number;
  log_ids: string[];
}

export interface StagingCustomer {
  id: string;
  batch_id: string;
  crm_customer_id: string;
  customer_code: string;
  customer_name: string;
  country: string | null;
  currency: string | null;
  sync_status: string;
  retry_count: number;
  created_at: string;
}

export interface StagingOrder {
  id: string;
  batch_id: string;
  crm_quotation_id: string;
  order_no: string;
  customer_code: string | null;
  total_amount: number | null;
  currency: string | null;
  sync_status: string;
  retry_count: number;
  created_at: string;
}

export interface ReconcileResult {
  checked_at: string;
  crm_customers: number;
  k3_customers: number;
  crm_orders: number;
  k3_orders: number;
  customer_diff: number;
  order_diff: number;
  consistent: boolean;
}

export interface TaskItem {
  id: string;
  title: string;
  content: string | null;
  biz_type: string | null;
  biz_id: string | null;
  assignee_id: string | null;
  due_date: string | null;
  priority: string;
  status: string;
  completed_at: string | null;
  created_at: string;
}

export interface ActivityItem {
  id: string;
  biz_type: string;
  biz_id: string | null;
  company_id: string | null;
  opportunity_id: string | null;
  type: string;
  content: string;
  happened_at: string | null;
  created_at: string;
}
