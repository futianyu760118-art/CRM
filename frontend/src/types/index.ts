export interface ApiEnvelope<T> {
  code: number;
  message: string;
  data: T;
  request_id: string;
}

export interface PageResult<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface MenuItem {
  code: string;
  name: string;
  path: string | null;
  icon: string | null;
  sort: number;
}

export interface CurrentUser {
  id: string;
  username: string;
  name: string;
  email: string | null;
  avatar: string | null;
  is_superuser: boolean;
  roles: string[];
  permissions: string[];
  department_id: string | null;
  department_name: string | null;
  menus: MenuItem[];
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface DashboardOverview {
  user: { id: string; name: string; roles: string[]; department: string | null };
  stats: Record<string, number>;
  todo: Record<string, number>;
  system: {
    users: number;
    departments: number;
    roles: number;
    today_operations: number;
  };
  opportunity_funnel: { stage: string; label: string; count: number }[];
  inquiry_statuses: string[];
  quotation_statuses: string[];
  feature_flags: Record<string, boolean>;
  milestone: { current: string; name: string; progress: number };
}

export interface SystemUser {
  id: string;
  username: string;
  code: string | null;
  name: string;
  email: string | null;
  phone: string | null;
  department_id: string | null;
  department_name: string | null;
  is_superuser: boolean;
  status: string;
  roles: string[];
  last_login_at: string | null;
  created_at: string;
}

export interface PermissionItem {
  id: string;
  code: string;
  name: string;
  module: string;
  type: string;
  parent_id: string | null;
  path: string | null;
  icon: string | null;
  sort: number;
  status: string;
}

export interface RoleItem {
  id: string;
  code: string;
  name: string;
  description: string | null;
  is_system: boolean;
  status: string;
  sort: number;
  permission_codes: string[];
  scope_type: string;
  created_at: string;
}

export interface DepartmentItem {
  id: string;
  code: string;
  name: string;
  parent_id: string | null;
  sort: number;
  status: string;
  remark: string | null;
  created_at: string;
  children?: DepartmentItem[];
}

export interface AuditLogItem {
  id: string;
  username: string | null;
  module: string;
  action: string;
  method: string;
  path: string;
  resource_id: string | null;
  status_code: number;
  success: boolean;
  duration_ms: number;
  ip: string | null;
  error_message: string | null;
  request_id: string | null;
  created_at: string;
}

export interface FeatureFlagItem {
  id: string;
  code: string;
  name: string;
  description: string | null;
  enabled: boolean;
  extra: Record<string, unknown> | null;
}

export interface DictionaryItem {
  id: string;
  dict_type: string;
  label: string;
  value: string;
  sort: number;
  enabled: boolean;
}
