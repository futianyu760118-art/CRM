'use client';

import { ApiOutlined, ReloadOutlined, SyncOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Row,
  Segmented,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { api, buildQuery } from '@/lib/api';
import { formatDateTime, formatNumber } from '@/lib/format';
import type { PageResult } from '@/types';
import type {
  IntegrationLog,
  ReconcileResult,
  StagingCustomer,
  StagingOrder,
} from '@/types/business';

function LogsTab() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<string | undefined>();

  const query = useQuery({
    queryKey: ['k3-logs', page, status],
    queryFn: () =>
      api.get<PageResult<IntegrationLog>>(
        `/integrations/k3/logs${buildQuery({ page, page_size: 10, status })}`,
      ),
  });

  const syncCustomers = useMutation({
    mutationFn: () => api.post('/integrations/k3/customer/sync', { limit: 50 }),
    onSuccess: (res) => {
      const r = res as { success: number; skipped: number; failed: number; batch_id: string };
      message.success(
        `客户同步完成：成功 ${r.success} / 跳过 ${r.skipped} / 失败 ${r.failed}（批次 ${r.batch_id}）`,
      );
      queryClient.invalidateQueries({ queryKey: ['k3-logs'] });
      queryClient.invalidateQueries({ queryKey: ['k3-customers'] });
      queryClient.invalidateQueries({ queryKey: ['customers'] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  const syncOrders = useMutation({
    mutationFn: () => api.post('/integrations/k3/order/sync', { limit: 50 }),
    onSuccess: (res) => {
      const r = res as { success: number; skipped: number; failed: number };
      message.success(`订单同步完成：成功 ${r.success} / 跳过 ${r.skipped} / 失败 ${r.failed}`);
      queryClient.invalidateQueries({ queryKey: ['k3-logs'] });
      queryClient.invalidateQueries({ queryKey: ['k3-orders'] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  const retry = useMutation({
    mutationFn: (id: string) => api.post(`/integrations/k3/retry/${id}`),
    onSuccess: (res) => {
      const r = res as { status: string; message: string };
      message.info(`${r.status}：${r.message}`);
      queryClient.invalidateQueries({ queryKey: ['k3-logs'] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  const columns: ColumnsType<IntegrationLog> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 170,
      render: (v: string) => formatDateTime(v),
    },
    { title: '系统', dataIndex: 'system', width: 80 },
    { title: '动作', dataIndex: 'action', width: 150 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (v: string) => <StatusTag value={v} />,
    },
    {
      title: '重试',
      dataIndex: 'retry_count',
      width: 90,
      render: (v: number, row) => `${v}/${row.max_retry}`,
    },
    {
      title: '幂等键',
      dataIndex: 'idempotency_key',
      ellipsis: true,
      render: (v: string | null) => <code style={{ fontSize: 11 }}>{v ?? '-'}</code>,
    },
    {
      title: '错误',
      dataIndex: 'error_message',
      ellipsis: true,
      render: (v: string | null) => v ?? '-',
    },
    {
      title: '操作',
      width: 90,
      render: (_, row) => (
        <HasPermission permission="integration:view">
          <Button
            size="small"
            disabled={row.status === 'SUCCESS'}
            loading={retry.isPending}
            onClick={() => retry.mutate(row.id)}
          >
            重试
          </Button>
        </HasPermission>
      ),
    },
  ];

  return (
    <>
      <Space wrap style={{ marginBottom: 12 }}>
        <Segmented
          value={status ?? 'ALL'}
          onChange={(v) => {
            setPage(1);
            setStatus(v === 'ALL' ? undefined : String(v));
          }}
          options={[
            { label: '全部', value: 'ALL' },
            { label: '成功', value: 'SUCCESS' },
            { label: '失败', value: 'FAILED' },
          ]}
        />
        <Button icon={<ReloadOutlined />} onClick={() => query.refetch()} />
        <HasPermission permission="integration:view">
          <Button
            type="primary"
            icon={<SyncOutlined />}
            loading={syncCustomers.isPending}
            onClick={() => syncCustomers.mutate()}
          >
            同步客户到 K3
          </Button>
          <Button
            icon={<SyncOutlined />}
            loading={syncOrders.isPending}
            onClick={() => syncOrders.mutate()}
          >
            同步订单到 K3
          </Button>
        </HasPermission>
      </Space>

      <Table<IntegrationLog>
        rowKey="id"
        size="small"
        loading={query.isFetching}
        columns={columns}
        dataSource={query.data?.items ?? []}
        scroll={{ x: 1200 }}
        pagination={{
          current: query.data?.page ?? 1,
          pageSize: query.data?.page_size ?? 10,
          total: query.data?.total ?? 0,
          onChange: setPage,
        }}
      />
    </>
  );
}

function CustomerStagingTab() {
  const query = useQuery({
    queryKey: ['k3-customers'],
    queryFn: () =>
      api.get<PageResult<StagingCustomer>>('/integrations/k3/customer-staging?page=1&page_size=50'),
  });

  const columns: ColumnsType<StagingCustomer> = [
    { title: '批次', dataIndex: 'batch_id', width: 230 },
    { title: '客户编码', dataIndex: 'customer_code', width: 130 },
    { title: '客户名称', dataIndex: 'customer_name' },
    { title: '国家', dataIndex: 'country', width: 120, render: (v) => v ?? '-' },
    { title: '币种', dataIndex: 'currency', width: 80, render: (v) => v ?? '-' },
    {
      title: '状态',
      dataIndex: 'sync_status',
      width: 110,
      render: (v: string) => <StatusTag value={v} />,
    },
    {
      title: '写入时间',
      dataIndex: 'created_at',
      width: 170,
      render: (v: string) => formatDateTime(v),
    },
  ];

  return (
    <Table<StagingCustomer>
      rowKey="id"
      size="small"
      loading={query.isFetching}
      columns={columns}
      dataSource={query.data?.items ?? []}
      pagination={false}
    />
  );
}

function OrderStagingTab() {
  const query = useQuery({
    queryKey: ['k3-orders'],
    queryFn: () =>
      api.get<PageResult<StagingOrder>>('/integrations/k3/order-staging?page=1&page_size=50'),
  });

  const columns: ColumnsType<StagingOrder> = [
    { title: '批次', dataIndex: 'batch_id', width: 230 },
    { title: '订单号', dataIndex: 'order_no', width: 170 },
    { title: '客户编码', dataIndex: 'customer_code', width: 130, render: (v) => v ?? '-' },
    {
      title: '金额',
      dataIndex: 'total_amount',
      width: 140,
      render: (v: number | null, row) => `${row.currency ?? ''} ${formatNumber(v, 2)}`,
    },
    {
      title: '状态',
      dataIndex: 'sync_status',
      width: 110,
      render: (v: string) => <StatusTag value={v} />,
    },
    {
      title: '写入时间',
      dataIndex: 'created_at',
      width: 170,
      render: (v: string) => formatDateTime(v),
    },
  ];

  return (
    <Table<StagingOrder>
      rowKey="id"
      size="small"
      loading={query.isFetching}
      columns={columns}
      dataSource={query.data?.items ?? []}
      pagination={false}
    />
  );
}

function ReconcileTab() {
  const { message } = App.useApp();
  const [result, setResult] = useState<ReconcileResult | null>(null);

  const run = useMutation({
    mutationFn: () => api.post<ReconcileResult>('/integrations/k3/reconcile'),
    onSuccess: (res) => {
      setResult(res);
      message.success('对账完成');
    },
    onError: (e: Error) => message.error(e.message),
  });

  return (
    <>
      <Space style={{ marginBottom: 12 }}>
        <Button type="primary" loading={run.isPending} onClick={() => run.mutate()}>
          执行对账
        </Button>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          每日比对 CRM 与 K3 的客户数、订单数，不一致时告警。
        </Typography.Text>
      </Space>
      {result ? (
        <>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={4}>
              <Card size="small">
                <Statistic title="CRM 客户" value={result.crm_customers} />
              </Card>
            </Col>
            <Col span={4}>
              <Card size="small">
                <Statistic title="K3 客户" value={result.k3_customers} />
              </Card>
            </Col>
            <Col span={4}>
              <Card size="small">
                <Statistic
                  title="客户差异"
                  value={result.customer_diff}
                  valueStyle={{ color: result.customer_diff > 0 ? '#faad14' : '#52c41a' }}
                />
              </Card>
            </Col>
            <Col span={4}>
              <Card size="small">
                <Statistic title="CRM 订单" value={result.crm_orders} />
              </Card>
            </Col>
            <Col span={4}>
              <Card size="small">
                <Statistic title="K3 订单" value={result.k3_orders} />
              </Card>
            </Col>
            <Col span={4}>
              <Card size="small">
                <Statistic
                  title="订单差异"
                  value={result.order_diff}
                  valueStyle={{ color: result.order_diff > 0 ? '#faad14' : '#52c41a' }}
                />
              </Card>
            </Col>
          </Row>
          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label="对账时间">{formatDateTime(result.checked_at)}</Descriptions.Item>
            <Descriptions.Item label="结论">
              {result.consistent ? (
                <Tag color="green">一致</Tag>
              ) : (
                <Tag color="orange">存在差异，请检查同步状态</Tag>
              )}
            </Descriptions.Item>
          </Descriptions>
        </>
      ) : (
        <Typography.Text type="secondary">点击「执行对账」查看结果</Typography.Text>
      )}
    </>
  );
}

export default function K3LogsPage() {
  return (
    <>
      <PageHeader
        title="K3 集成日志"
        description="中间表写入 / 幂等 / 重试 / 对账（对应 F-24、F-25）"
        extra={<ApiOutlined style={{ fontSize: 20, color: '#1677ff' }} />}
      />
      <Tabs
        items={[
          { key: 'logs', label: '集成日志', children: <LogsTab /> },
          { key: 'customers', label: '客户中间表', children: <CustomerStagingTab /> },
          { key: 'orders', label: '订单中间表', children: <OrderStagingTab /> },
          { key: 'reconcile', label: '对账', children: <ReconcileTab /> },
        ]}
      />
    </>
  );
}
