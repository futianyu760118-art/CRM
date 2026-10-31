'use client';

import { MergeCellsOutlined, PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Form, Input, Modal, Select, Space, Table, Tabs, Tag, Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import Link from 'next/link';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { api, buildQuery } from '@/lib/api';
import {
  CUSTOMER_GROUPS,
  CUSTOMER_SOURCE_OPTIONS,
  CUSTOMER_SOURCES,
  CUSTOMER_TYPES,
  CUSTOMER_TYPE_OPTIONS,
  PAYMENT_METHOD_OPTIONS,
  PAYMENT_METHODS,
  labelOf,
} from '@/lib/dictionaries';
import { formatDateTime } from '@/lib/format';
import type { PageResult } from '@/types';
import type { Company, CustomerGroupSummary } from '@/types/business';

export default function CustomersPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [level, setLevel] = useState<string | undefined>();
  const [group, setGroup] = useState('all');
  const [source, setSource] = useState<string | undefined>();
  const [customerType, setCustomerType] = useState<string | undefined>();
  const [paymentMethod, setPaymentMethod] = useState<string | undefined>();
  const [createOpen, setCreateOpen] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [form] = Form.useForm();
  const [mergeForm] = Form.useForm<{ keep_id: string; source_ids: string[] }>();

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['customers', page, keyword, level, group, source, customerType, paymentMethod],
    queryFn: () =>
      api.get<PageResult<Company>>(
        `/customers${buildQuery({
          page,
          page_size: 10,
          keyword,
          customer_level: level,
          group: group === 'all' ? undefined : group,
          source,
          customer_type: customerType,
          payment_method: paymentMethod,
        })}`,
      ),
  });

  const { data: groupSummary } = useQuery({
    queryKey: ['customer-group-summary'],
    queryFn: () => api.get<CustomerGroupSummary>('/customers/groups/summary'),
  });

  const { data: duplicates } = useQuery({
    queryKey: ['customer-duplicates'],
    queryFn: () => api.get<{ key: string; companies: Company[] }[]>('/customers/duplicates'),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['customers'] });
    queryClient.invalidateQueries({ queryKey: ['customer-group-summary'] });
  };

  const createMutation = useMutation({
    mutationFn: (values: Partial<Company>) => api.post('/customers', values),
    onSuccess: () => {
      message.success('客户创建成功');
      setCreateOpen(false);
      form.resetFields();
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const mergeMutation = useMutation({
    mutationFn: (values: { keep_id: string; source_ids: string[] }) => api.post('/customers/merge', values),
    onSuccess: (res) => {
      const result = res as { merged: number; moved_contacts: number };
      message.success(`已合并 ${result.merged} 个客户，迁移联系人 ${result.moved_contacts} 个`);
      setMergeOpen(false);
      mergeForm.resetFields();
      invalidate();
      queryClient.invalidateQueries({ queryKey: ['customer-duplicates'] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  const columns: ColumnsType<Company> = [
    {
      title: '客户编码',
      dataIndex: 'code',
      width: 130,
      render: (v: string, row) => <Link href={`/customers/${row.id}`}>{v}</Link>,
    },
    {
      title: '客户名称',
      dataIndex: 'name',
      ellipsis: true,
      render: (v: string, row) => <Link href={`/customers/${row.id}`}>{v}</Link>,
    },
    { title: '国家', dataIndex: 'country', width: 100, render: (v) => v ?? '-' },
    {
      title: '分组',
      dataIndex: 'customer_group',
      width: 100,
      render: (v: string | null, row) =>
        v ? (
          <Tooltip title={row.group_reason}>
            <Tag color={v === 'new' ? 'green' : v === 'dormant' ? 'default' : 'blue'}>
              {labelOf(CUSTOMER_GROUPS, v)}
            </Tag>
          </Tooltip>
        ) : (
          '-'
        ),
    },
    {
      title: '来源',
      dataIndex: 'source',
      width: 100,
      render: (v: string | null) => labelOf(CUSTOMER_SOURCES, v),
    },
    {
      title: '类型',
      dataIndex: 'customer_type',
      width: 100,
      render: (v: string | null) => labelOf(CUSTOMER_TYPES, v),
    },
    {
      title: '付款方式',
      dataIndex: 'payment_method',
      width: 110,
      render: (v: string | null) => labelOf(PAYMENT_METHODS, v),
    },
    {
      title: '主要联系人',
      dataIndex: 'primary_contact',
      width: 170,
      render: (v: { name: string; contact_value: string | null } | null) =>
        v ? (
          <span>
            {v.name}
            {v.contact_value ? <Tag style={{ marginLeft: 6 }}>{v.contact_value}</Tag> : null}
          </span>
        ) : (
          '-'
        ),
    },
    {
      title: '负责人',
      dataIndex: 'owner_name',
      width: 100,
      render: (v: string | null | undefined) => v ?? '-',
    },
    {
      title: '等级',
      dataIndex: 'customer_level',
      width: 80,
      render: (v: string | null) => (v ? <Tag color="blue">{v}</Tag> : '-'),
    },
    { title: '联系人', dataIndex: 'contact_count', width: 80 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: string) => <StatusTag value={v} />,
    },
    {
      title: 'K3 同步',
      dataIndex: 'sync_status',
      width: 110,
      render: (v: string | null) => (v ? <StatusTag value={v} /> : '-'),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (v: string) => formatDateTime(v),
    },
  ];

  return (
    <>
      <PageHeader
        title="客户管理"
        description="客户建档 / 去重合并 / K3 同步状态（对应 F-05、F-06）"
        extra={
          <Space wrap>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="名称/编码/国家"
              style={{ width: 200 }}
              onPressEnter={(e) => {
                setPage(1);
                setKeyword((e.target as HTMLInputElement).value);
              }}
            />
            <Select
              allowClear
              placeholder="等级"
              style={{ width: 100 }}
              value={level}
              onChange={(v) => {
                setPage(1);
                setLevel(v);
              }}
              options={['A', 'B', 'C', 'D'].map((v) => ({ value: v, label: `${v} 类` }))}
            />
            <Select
              allowClear
              placeholder="来源"
              style={{ width: 110 }}
              value={source}
              onChange={(v) => {
                setPage(1);
                setSource(v);
              }}
              options={CUSTOMER_SOURCE_OPTIONS}
            />
            <Select
              allowClear
              placeholder="客户类型"
              style={{ width: 120 }}
              value={customerType}
              onChange={(v) => {
                setPage(1);
                setCustomerType(v);
              }}
              options={CUSTOMER_TYPE_OPTIONS}
            />
            <Select
              allowClear
              placeholder="付款方式"
              style={{ width: 130 }}
              value={paymentMethod}
              onChange={(v) => {
                setPage(1);
                setPaymentMethod(v);
              }}
              options={PAYMENT_METHOD_OPTIONS}
            />
            <Button icon={<ReloadOutlined />} onClick={() => refetch()} />
            <HasPermission permission="customer:merge">
              <Button
                icon={<MergeCellsOutlined />}
                onClick={() => setMergeOpen(true)}
                disabled={!duplicates?.length}
              >
                去重合并{duplicates?.length ? `(${duplicates.length})` : ''}
              </Button>
            </HasPermission>
            <HasPermission permission="customer:create">
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
                新建客户
              </Button>
            </HasPermission>
          </Space>
        }
      />

      <Tabs
        activeKey={group}
        onChange={(v) => {
          setPage(1);
          setGroup(v);
        }}
        items={[
          { key: 'all', label: `全部 (${groupSummary?.all ?? 0})` },
          { key: 'new', label: `新客户 (${groupSummary?.new ?? 0})` },
          { key: 'active', label: `活跃客户 (${groupSummary?.active ?? 0})` },
          { key: 'dormant', label: `休眠客户 (${groupSummary?.dormant ?? 0})` },
        ]}
      />

      <Table<Company>
        rowKey="id"
        size="small"
        loading={isFetching}
        columns={columns}
        dataSource={data?.items ?? []}
        scroll={{ x: 1500 }}
        pagination={{
          current: data?.page ?? 1,
          pageSize: data?.page_size ?? 10,
          total: data?.total ?? 0,
          onChange: setPage,
        }}
      />

      <Modal
        title="新建客户"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending}
        destroyOnClose
      >
        <Form form={form} layout="vertical" requiredMark={false} onFinish={(v) => createMutation.mutate(v)}>
          <Form.Item name="name" label="客户名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="name_en" label="英文名称">
            <Input />
          </Form.Item>
          <Form.Item name="country" label="国家">
            <Input />
          </Form.Item>
          <Form.Item
            name="currency"
            label="默认币种"
            initialValue="USD"
            tooltip="同客户新增其他币种时，系统自动追加业务编码 -1 / -2 …"
          >
            <Select
              options={['USD', 'EUR', 'CNY', 'GBP', 'JPY'].map((v) => ({ value: v, label: v }))}
            />
          </Form.Item>
          <Form.Item name="industry" label="行业">
            <Input />
          </Form.Item>
          <Form.Item name="customer_level" label="等级">
            <Select
              allowClear
              options={['A', 'B', 'C', 'D'].map((v) => ({ value: v, label: `${v} 类` }))}
            />
          </Form.Item>
          <Form.Item name="source" label="客户来源" initialValue="OTHER">
            <Select options={CUSTOMER_SOURCE_OPTIONS} />
          </Form.Item>
          <Form.Item name="customer_type" label="客户类型" initialValue="OTHER">
            <Select options={CUSTOMER_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item name="payment_method" label="付款方式">
            <Select allowClear options={PAYMENT_METHOD_OPTIONS} />
          </Form.Item>
          <Form.Item name="brand" label="品牌">
            <Input />
          </Form.Item>
          <Form.Item name="main_products" label="主营产品">
            <Input />
          </Form.Item>
          <Form.Item name="sales_channel_market" label="销售渠道及市场">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="website" label="官网" tooltip="需以 http:// 或 https:// 开头">
            <Input />
          </Form.Item>
          <Form.Item name="address" label="地址">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="company_background" label="公司背景">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="客户去重合并"
        open={mergeOpen}
        onCancel={() => setMergeOpen(false)}
        onOk={() => mergeForm.submit()}
        confirmLoading={mergeMutation.isPending}
        width={640}
        destroyOnClose
      >
        {(duplicates ?? []).length === 0 ? (
          <div>未检测到重复客户</div>
        ) : (
          <Form form={mergeForm} layout="vertical" onFinish={(v) => mergeMutation.mutate(v)}>
            <Form.Item name="keep_id" label="保留的客户（主客户）" rules={[{ required: true }]}>
              <Select
                placeholder="选择要保留的客户"
                options={(duplicates ?? []).flatMap((g) =>
                  g.companies.map((c) => ({
                    value: c.id,
                    label: `${c.name}（${c.code}）`,
                  })),
                )}
              />
            </Form.Item>
            <Form.Item name="source_ids" label="合并掉的客户" rules={[{ required: true }]}>
              <Select
                mode="multiple"
                placeholder="选择要合并的客户"
                options={(duplicates ?? []).flatMap((g) =>
                  g.companies.map((c) => ({ value: c.id, label: `${c.name}（${c.code}）` })),
                )}
              />
            </Form.Item>
          </Form>
        )}
      </Modal>
    </>
  );
}
