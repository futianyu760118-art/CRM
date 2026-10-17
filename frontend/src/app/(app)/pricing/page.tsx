'use client';

import { ReloadOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Segmented, Space, Table, Tabs, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import Link from 'next/link';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { api, buildQuery } from '@/lib/api';
import { formatDateTime, formatNumber } from '@/lib/format';
import type { PageResult } from '@/types';
import type { Pricing, PricingRule } from '@/types/business';

function RecordsTab() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<string | undefined>();

  const query = useQuery({
    queryKey: ['pricing-list', page, status],
    queryFn: () =>
      api.get<PageResult<Pricing>>(`/pricing${buildQuery({ page, page_size: 10, status })}`),
  });

  const submit = useMutation({
    mutationFn: (id: string) => api.post(`/pricing/${id}/submit`),
    onSuccess: () => {
      message.success('已提交审批');
      queryClient.invalidateQueries({ queryKey: ['pricing-list'] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  const columns: ColumnsType<Pricing> = [
    {
      title: '核价单',
      dataIndex: 'id',
      width: 110,
      render: (_: string, row) => <Link href={`/pricing/${row.id}`}>查看</Link>,
    },
    { title: '询价单号', dataIndex: 'inquiry_no', width: 170, render: (v) => v ?? '-' },
    { title: '客户', dataIndex: 'company_name', ellipsis: true, render: (v) => v ?? '-' },
    { title: '版本', dataIndex: 'version', width: 70, render: (v: number) => `V${v}` },
    {
      title: '状态',
      dataIndex: 'status',
      width: 120,
      render: (v: string) => <StatusTag value={v} />,
    },
    {
      title: '总成本',
      dataIndex: 'total_cost',
      width: 120,
      render: (v: number | null) => (v === null ? <Tag color="red">无权限</Tag> : formatNumber(v, 2)),
    },
    {
      title: '底价',
      dataIndex: 'floor_price',
      width: 110,
      render: (v: number | null) => (v === null ? <Tag color="red">无权限</Tag> : formatNumber(v, 4)),
    },
    {
      title: '最终价',
      dataIndex: 'final_price',
      width: 110,
      render: (v: number | null) => formatNumber(v, 2),
    },
    {
      title: '折扣率',
      dataIndex: 'discount_rate',
      width: 90,
      render: (v: number | null) => (v == null ? '1' : String(v)),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: '操作',
      width: 110,
      render: (_, row) => (
        <HasPermission permission="pricing:submit">
          <Button
            size="small"
            disabled={row.status !== 'DRAFT'}
            loading={submit.isPending}
            onClick={() => submit.mutate(row.id)}
          >
            提交
          </Button>
        </HasPermission>
      ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 12 }}>
        <Segmented
          value={status ?? 'ALL'}
          onChange={(v) => {
            setPage(1);
            setStatus(v === 'ALL' ? undefined : String(v));
          }}
          options={[
            { label: '全部', value: 'ALL' },
            { label: '草稿', value: 'DRAFT' },
            { label: '待审批', value: 'PENDING_APPROVAL' },
            { label: '已通过', value: 'APPROVED' },
          ]}
        />
        <Button icon={<ReloadOutlined />} onClick={() => query.refetch()} />
      </Space>
      <Table<Pricing>
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

function RulesTab() {
  const query = useQuery({
    queryKey: ['pricing-rules'],
    queryFn: () => api.get<PageResult<PricingRule>>('/pricing-rules?page=1&page_size=50'),
  });

  const columns: ColumnsType<PricingRule> = [
    { title: '规则编码', dataIndex: 'code', width: 180 },
    { title: '名称', dataIndex: 'name' },
    {
      title: '条件',
      dataIndex: 'conditions',
      render: (v: Record<string, unknown> | null) => (
        <code style={{ fontSize: 12 }}>{JSON.stringify(v)}</code>
      ),
    },
    {
      title: '动作',
      dataIndex: 'actions',
      render: (v: Record<string, unknown> | null) => (
        <code style={{ fontSize: 12 }}>{JSON.stringify(v)}</code>
      ),
    },
    { title: '优先级', dataIndex: 'priority', width: 90 },
    {
      title: '启用',
      dataIndex: 'enabled',
      width: 90,
      render: (v: boolean) => <StatusTag value={v ? 'ACTIVE' : 'INACTIVE'} />,
    },
  ];

  return (
    <>
      <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
        核价规则引擎（P1）：条件为 JSON（支持 eq / in / gte / lte / contains），动作为 margin、margin_delta（规则只调利润率，不直接乘最终价）。
      </Typography.Paragraph>
      <Table<PricingRule>
        rowKey="id"
        size="small"
        loading={query.isFetching}
        columns={columns}
        dataSource={query.data?.items ?? []}
        pagination={false}
      />
    </>
  );
}

export default function PricingPage() {
  return (
    <>
      <PageHeader
        title="核价管理"
        description="成本核算 / 版本不覆盖 / 成本与底价字段级权限（对应 F-12、F-13）"
      />
      <Tabs
        items={[
          { key: 'records', label: '核价记录', children: <RecordsTab /> },
          { key: 'rules', label: '核价规则', children: <RulesTab /> },
        ]}
      />
    </>
  );
}
