import type { ReactNode } from 'react';
import {
  AimOutlined,
  ApiOutlined,
  AppstoreOutlined,
  AuditOutlined,
  CalculatorOutlined,
  CheckSquareOutlined,
  ContactsOutlined,
  DashboardOutlined,
  FileSearchOutlined,
  FunnelPlotOutlined,
  MailOutlined,
  ProfileOutlined,
  SettingOutlined,
  TeamOutlined,
} from '@ant-design/icons';

const ICONS: Record<string, ReactNode> = {
  DashboardOutlined: <DashboardOutlined />,
  FunnelPlotOutlined: <FunnelPlotOutlined />,
  TeamOutlined: <TeamOutlined />,
  ContactsOutlined: <ContactsOutlined />,
  AimOutlined: <AimOutlined />,
  AppstoreOutlined: <AppstoreOutlined />,
  FileSearchOutlined: <FileSearchOutlined />,
  CalculatorOutlined: <CalculatorOutlined />,
  ProfileOutlined: <ProfileOutlined />,
  AuditOutlined: <AuditOutlined />,
  MailOutlined: <MailOutlined />,
  CheckSquareOutlined: <CheckSquareOutlined />,
  ApiOutlined: <ApiOutlined />,
  SettingOutlined: <SettingOutlined />,
};

export function renderIcon(name: string | null): ReactNode {
  if (!name) return undefined;
  return ICONS[name] ?? undefined;
}
