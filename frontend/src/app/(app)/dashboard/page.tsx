'use client';

import {
  AuditOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Alert, Card, Col, List, Progress, Row, Skeleton, Space, Statistic, Tag, Typography } from 'antd';

import { api } from '@/lib/api';
import { useAuthStore } from '@/lib/auth-store';
import type { DashboardOverview } from '@/types';

const BUSINESS_STATS: { key: string; label: string; milestone: string }[] = [
  { key: 'leads', label: '线索', milestone: 'M2' },
  { key: 'customers', label: '客户', milestone: 'M2' },
  { key: 'opportunities', label: '商机', milestone: 'M3' },
  { key: 'inquiries', label: '询价', milestone: 'M3' },
  { key: 'quotations', label: '报价', milestone: 'M4' },
  { key: 'pending_approvals', label: '待审批', milestone: 'M4' },
];

export default function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => api.get<DashboardOverview>('/dashboard'),
  });

  if (isLoading) {
    return <Skeleton active paragraph={{ rows: 8 }} />;
  }

  if (error || !data) {
    return <Alert type="error" showIcon message="工作台数据加载失败" />;
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space size={8} wrap>
        <Typography.Title level={4} style={{ margin: 0 }}>
          工作台
        </Typography.Title>
        <Tag color="processing">
          当前里程碑 {data.milestone.current} · {data.milestone.name}
        </Tag>
      </Space>

      <Alert
        type="info"
        showIcon
        message={`${data.user.name}，欢迎回来。当前身份：${data.user.roles.join(' / ') || '未分配角色'}${data.user.department ? ` · ${data.user.department}` : ''}`}
      />

      <Row gutter={[16, 16]}>
        {BUSINESS_STATS.map((item) => (
          <Col key={item.key} xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic title={item.label} value={data.stats[item.key] ?? 0} />
              <Tag color="default" style={{ marginTop: 8 }}>
                {item.milestone}
              </Tag>
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card title="系统概览" size="small" extra={<Tag color="green">M1 已交付</Tag>}>
            <Row gutter={[16, 16]}>
              <Col span={8}>
                <Statistic
                  title="系统用户"
                  value={data.system.users}
                  prefix={<TeamOutlined />}
                />
              </Col>
              <Col span={8}>
                <Statistic title="部门数" value={data.system.departments} />
              </Col>
              <Col span={8}>
                <Statistic title="角色数" value={data.system.roles} prefix={<AuditOutlined />} />
              </Col>
              <Col span={24}>
                <Statistic
                  title="今日操作数（审计）"
                  value={data.system.today_operations}
                  prefix={<CheckCircleOutlined />}
                />
              </Col>
            </Row>
          </Card>
        </Col>

        <Col xs={24} md={12}>
          <Card title="里程碑进度" size="small" extra={<ClockCircleOutlined />}>
            <Progress percent={data.milestone.progress} status="active" />
            <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
              M1 系统骨架：登录 / 权限 / Layout / Dashboard / 审计 / 编号规则 / 状态机
            </Typography.Paragraph>
            <List
              size="small"
              style={{ marginTop: 12 }}
              dataSource={[
                { m: 'M2', t: '客户中心：线索→客户→联系人' },
                { m: 'M3', t: '销售主链路：商机→询价→跟进' },
                { m: 'M4', t: '询报价闭环：核价→报价→审批→PDF' },
                { m: 'M5', t: '邮件闭环：发送→回复→IMAP→关联' },
                { m: 'M6', t: '集成+UAT：K3 PoC、测试、验收' },
              ]}
              renderItem={(item) => (
                <List.Item>
                  <Tag>{item.m}</Tag>
                  {item.t}
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>

      <Card title="功能开关（Feature Flag）" size="small">
        <Space size={[8, 8]} wrap>
          {Object.entries(data.feature_flags).map(([code, enabled]) => (
            <Tag key={code} color={enabled ? 'green' : 'default'}>
              {code}: {enabled ? 'ON' : 'OFF'}
            </Tag>
          ))}
        </Space>
      </Card>
    </Space>
  );
}
