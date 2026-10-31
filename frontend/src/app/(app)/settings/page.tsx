'use client';

import {
  AuditOutlined,
  FlagOutlined,
  ProfileOutlined,
  TeamOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { Card, Col, Row, Typography, Space } from 'antd';
import Link from 'next/link';

const ENTRIES = [
  {
    href: '/settings/users',
    title: '用户管理',
    desc: '账号、角色分配、部门归属',
    icon: <UserOutlined />,
  },
  {
    href: '/settings/roles',
    title: '角色与权限',
    desc: 'RBAC 权限点、数据范围（DataScope）',
    icon: <TeamOutlined />,
  },
  {
    href: '/settings/departments',
    title: '组织架构',
    desc: '部门树、上下级关系',
    icon: <ProfileOutlined />,
  },
  {
    href: '/settings/dictionaries',
    title: '数据字典',
    desc: '枚举值统一维护（varchar + 字典表）',
    icon: <ProfileOutlined />,
  },
  {
    href: '/settings/audit-logs',
    title: '审计日志',
    desc: '所有写操作留痕、可追溯',
    icon: <AuditOutlined />,
  },
  {
    href: '/settings/feature-flags',
    title: '功能开关',
    desc: '按里程碑灰度开放模块',
    icon: <FlagOutlined />,
  },
];

export default function SettingsPage() {
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={4} style={{ margin: 0 }}>
        系统设置
      </Typography.Title>
      <Row gutter={[16, 16]}>
        {ENTRIES.map((item) => (
          <Col key={item.href} xs={24} sm={12} md={8}>
            <Link href={item.href}>
              <Card hoverable size="small">
                <Space direction="vertical" size={4}>
                  <Space>
                    {item.icon}
                    <Typography.Text strong>{item.title}</Typography.Text>
                  </Space>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {item.desc}
                  </Typography.Text>
                </Space>
              </Card>
            </Link>
          </Col>
        ))}
      </Row>
    </Space>
  );
}
