'use client';

import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { App, Button, Card, Form, Input, Space, Typography } from 'antd';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { useAuthStore } from '@/lib/auth-store';

interface LoginForm {
  username: string;
  password: string;
}

const DEMO_ACCOUNTS = [
  { label: '管理员', username: 'admin', password: 'admin123' },
  { label: '业务员', username: 'sales', password: 'sales123' },
  { label: '销售主管', username: 'manager', password: 'manager123' },
  { label: '核价员', username: 'pricing', password: 'pricing123' },
  { label: '老板', username: 'boss', password: 'boss123' },
];

export default function LoginPage() {
  const router = useRouter();
  const { message } = App.useApp();
  const [form] = Form.useForm<LoginForm>();
  const login = useAuthStore((s) => s.login);
  const accessToken = useAuthStore((s) => s.accessToken);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (accessToken) {
      router.replace('/dashboard');
    }
  }, [accessToken, router]);

  const onFinish = async (values: LoginForm) => {
    setLoading(true);
    try {
      const user = await login(values.username, values.password);
      message.success(`欢迎回来，${user.name}`);
      router.replace('/dashboard');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '登录失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #1677ff 0%, #0958d9 100%)',
      }}
    >
      <Card style={{ width: 420, boxShadow: '0 8px 32px rgba(0,0,0,0.18)' }}>
        <Space direction="vertical" size={4} style={{ width: '100%', textAlign: 'center' }}>
          <Typography.Title level={3} style={{ marginBottom: 0 }}>
            外贸销售CRM
          </Typography.Title>
          <Typography.Text type="secondary">询报价管理平台 · CRM-2026-001</Typography.Text>
        </Space>

        <Form<LoginForm>
          form={form}
          layout="vertical"
          onFinish={onFinish}
          requiredMark={false}
          style={{ marginTop: 24 }}
          initialValues={{ username: 'admin', password: 'admin123' }}
        >
          <Form.Item
            name="username"
            label="账号"
            rules={[{ required: true, message: '请输入账号' }]}
          >
            <Input prefix={<UserOutlined />} placeholder="用户名" size="large" autoComplete="username" />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码"
              size="large"
              autoComplete="current-password"
            />
          </Form.Item>
          <Form.Item style={{ marginBottom: 12 }}>
            <Button type="primary" htmlType="submit" size="large" block loading={loading}>
              登录
            </Button>
          </Form.Item>
        </Form>

        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          演示账号（点击填充）：
        </Typography.Text>
        <div style={{ marginTop: 8 }}>
          <Space size={[8, 8]} wrap>
            {DEMO_ACCOUNTS.map((acc) => (
              <Button
                key={acc.username}
                size="small"
                onClick={() =>
                  form.setFieldsValue({ username: acc.username, password: acc.password })
                }
              >
                {acc.label} / {acc.username}
              </Button>
            ))}
          </Space>
        </div>
      </Card>
    </div>
  );
}
