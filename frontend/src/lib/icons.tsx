import type { ReactNode } from 'react';
import {
  AimOutlined,
  ApiOutlined,
  AppstoreOutlined,
  AuditOutlined,
  BugOutlined,
  CalculatorOutlined,
  CheckSquareOutlined,
  ContactsOutlined,
  DashboardOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  FunnelPlotOutlined,
  GoldOutlined,
  MailOutlined,
  ProfileOutlined,
  SettingOutlined,
  ShoppingCartOutlined,
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
  ShoppingCartOutlined: <ShoppingCartOutlined />,
  ExperimentOutlined: <ExperimentOutlined />,
  GoldOutlined: <GoldOutlined />,
  BugOutlined: <BugOutlined />,
  SettingOutlined: <SettingOutlined />,
};

export function renderIcon(name: string | null): ReactNode {
  if (!name) return undefined;
  return ICONS[name] ?? undefined;
}
