'use client';

import { Layout } from 'antd';
import { useState, type ReactNode } from 'react';

import { useAuthStore } from '@/lib/auth-store';

import HeaderBar from './HeaderBar';
import SideMenu from './SideMenu';

const { Sider, Content } = Layout;

export function AppShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const user = useAuthStore((s) => s.user);

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme="dark"
        width={220}
      >
        <div
          style={{
            height: 56,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontWeight: 600,
            letterSpacing: 1,
          }}
        >
          {collapsed ? 'CRM' : '外贸销售 CRM'}
        </div>
        <SideMenu menus={user?.menus ?? []} />
      </Sider>
      <Layout>
        <HeaderBar collapsed={collapsed} />
        <Content style={{ margin: 16 }}>
          <div
            style={{
              background: '#fff',
              padding: 16,
              borderRadius: 8,
              minHeight: 'calc(100vh - 120px)',
            }}
          >
            {children}
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}

export default AppShell;
