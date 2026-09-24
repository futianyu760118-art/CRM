'use client';

import { LogoutOutlined, UserOutlined } from '@ant-design/icons';
import { App, Avatar, Dropdown, Layout, Space, Tag, Typography } from 'antd';
import { useRouter } from 'next/navigation';

import { useAuthStore } from '@/lib/auth-store';

const { Header } = Layout;

export function HeaderBar({ collapsed }: { collapsed: boolean }) {
  const router = useRouter();
  const { modal } = App.useApp();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const onLogout = () => {
    modal.confirm({
      title: '确认退出登录？',
      okText: '退出',
      cancelText: '取消',
      onOk: async () => {
        await logout();
        router.replace('/login');
      },
    });
  };

  return (
    <Header
      style={{
        background: '#fff',
        padding: '0 24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        borderBottom: '1px solid #f0f0f0',
      }}
    >
      <Typography.Text strong style={{ fontSize: 16 }}>
        {collapsed ? '' : '外贸销售CRM及询报价管理平台'}
      </Typography.Text>

      <Space size={12}>
        {(user?.roles ?? []).map((role) => (
          <Tag key={role} color="blue">
            {role}
          </Tag>
        ))}
        <Dropdown
          menu={{
            items: [
              { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: onLogout },
            ],
          }}
        >
          <Space style={{ cursor: 'pointer' }}>
            <Avatar size="small" icon={<UserOutlined />} />
            <span>
              {user?.name}
              {user?.department_name ? ` · ${user.department_name}` : ''}
            </span>
          </Space>
        </Dropdown>
      </Space>
    </Header>
  );
}

export default HeaderBar;
