'use client';

import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { api, buildQuery } from '@/lib/api';
import { formatDateTime, formatNumber } from '@/lib/format';
import type { PageResult } from '@/types';
import type { QuoteLibrary, QuoteStats } from '@/types/sales';

const CERTIFICATE_LEVELS = ['CE', 'ROHS', 'CCC', 'UL', 'ETL', '国标', '行标', '企标', '无证书'];

interface FormValues {
  external_model: string;
  certificate_level?: string;
  internal_model?: string;
  product_name?: string;
  category?: string;
  power?: string;
  configuration?: string;
  specs?: string;
  price_rmb?: number | null;
  price_usd?: number | null;
  unit_price?: number | null;
  min_price?: number | null;
  validity_days?: number;
  source_inquiry_no?: string;
  remark?: string;
}

export default function QuoteLibraryPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [cert, setCert] = useState<string | undefined>();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<QuoteLibrary | null>(null);
  const [form] = Form.useForm<FormValues>();

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['quote-library', page, keyword, cert],
    queryFn: () =>
      api.get<PageResult<QuoteLibrary>>(
        `/quote-library${buildQuery({ page, page_size: 10, keyword, certificate_level: cert })}`,
      ),
  });

  const { data: stats } = useQuery({
    queryKey: ['quote-stats'],
    queryFn: () => api.get<QuoteStats>('/quote-library/stats'),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['quote-library'] });
  const invalidateStats = () => queryClient.invalidateQueries({ queryKey: ['quote-stats'] });

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (row: QuoteLibrary) => {
    setEditing(row);
    form.setFieldsValue({
      external_model: row.external_model,
      certificate_level: row.certificate_level,
      internal_model: row.internal_model ?? undefined,
      product_name: row.product_name ?? undefined,
      category: row.category ?? undefined,
      power: row.power ?? undefined,
      configuration: row.configuration ?? undefined,
      specs: row.specs ?? undefined,
      price_rmb: row.price_rmb ?? undefined,
      price_usd: row.price_usd ?? undefined,
      unit_price: row.unit_price ?? undefined,
      min_price: row.min_price ?? undefined,
      validity_days: row.validity_days,
      remark: row.remark ?? undefined,
    });
    setModalOpen(true);
  };

  const saveMutation = useMutation({
    mutationFn: (values: FormValues) =>
      editing ? api.put(`/quote-library/${editing.id}`, values) : api.post('/quote-library', values),
    onSuccess: () => {
      message.success(editing ? '报价库条目已更新' : '报价库条目已创建');
      setModalOpen(false);
      invalidate();
      invalidateStats();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/quote-library/${id}`),
    onSuccess: () => {
      message.success('报价库条目已删除');
      invalidate();
      invalidateStats();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const columns: ColumnsType<QuoteLibrary> = [
    { title: '外部型号', dataIndex: 'external_model', width: 160, fixed: 'left' },
    { title: '证书等级', dataIndex: 'certificate_level', width: 100, render: (v) => v || '-' },
    { title: '内部型号', dataIndex: 'internal_model', width: 130, render: (v) => v ?? '-' },
    { title: '产品名称', dataIndex: 'product_name', ellipsis: true, render: (v) => v ?? '-' },
    { title: '类目', dataIndex: 'category', width: 110, render: (v) => v ?? '-' },
    { title: '功率', dataIndex: 'power', width: 100, render: (v) => v ?? '-' },
    { title: '人民币价', dataIndex: 'price_rmb', width: 110, render: (v) => formatNumber(v, 2) },
    { title: '美元价', dataIndex: 'price_usd', width: 110, render: (v) => formatNumber(v, 2) },
    { title: '有效期(天)', dataIndex: 'validity_days', width: 100 },
    { title: '引用次数', dataIndex: 'usage_count', width: 90 },
    { title: '维护人', dataIndex: 'creator', width: 100, render: (v) => v ?? '-' },
    {
      title: '同步',
      dataIndex: 'sync_status',
      width: 100,
      render: (v: string) => <StatusTag value={v} />,
    },
    { title: '创建时间', dataIndex: 'created_at', width: 160, render: (v) => formatDateTime(v) },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      fixed: 'right',
      render: (_, row) => (
        <Space size={0}>
          <HasPermission permission="quote:manage">
            <Button type="link" size="small" onClick={() => openEdit(row)}>
              编辑
            </Button>
          </HasPermission>
          <HasPermission permission="quote:delete">
            <Popconfirm title="确认删除该报价库条目？" onConfirm={() => deleteMutation.mutate(row.id)}>
              <Button type="link" size="small" danger>
                删除
              </Button>
            </Popconfirm>
          </HasPermission>
        </Space>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="报价库"
        description="外部型号 → 内部型号映射与价格维护（AC-M3）"
        extra={
          <Space wrap>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="外部型号/产品名/类目/内部型号"
              style={{ width: 240 }}
              onPressEnter={(e) => {
                setPage(1);
                setKeyword((e.target as HTMLInputElement).value);
              }}
            />
            <Select
              allowClear
              placeholder="证书等级"
              style={{ width: 130 }}
              value={cert}
              onChange={(v) => {
                setPage(1);
                setCert(v);
              }}
              options={CERTIFICATE_LEVELS.map((v) => ({ value: v, label: v }))}
            />
            <Button icon={<ReloadOutlined />} onClick={() => refetch()} />
            <HasPermission permission="quote:manage">
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                新建条目
              </Button>
            </HasPermission>
          </Space>
        }
      />

      {stats ? (
        <Space wrap style={{ marginBottom: 12 }}>
          <Tag color="geekblue">共 {data?.total ?? 0} 条</Tag>
          {Object.entries(stats.by_certificate_level).map(([c, n]) => (
            <Tag key={c}>{c || '无证书'} {n}</Tag>
          ))}
          {Object.entries(stats.by_category).map(([c, n]) => (
            <Tag key={c} color="cyan">
              {c} {n}
            </Tag>
          ))}
        </Space>
      ) : null}

      <Table<QuoteLibrary>
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
        title={editing ? '编辑报价库条目' : '新建报价库条目'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={saveMutation.isPending}
        destroyOnClose
        width={680}
      >
        <Form form={form} layout="vertical" requiredMark={false} onFinish={(v) => saveMutation.mutate(v)}>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="external_model" label="外部型号" rules={[{ required: true }]}>
              <Input disabled={!!editing} style={{ width: 220 }} />
            </Form.Item>
            <Form.Item name="certificate_level" label="证书等级" initialValue="">
              <Select
                allowClear
                style={{ width: 140 }}
                options={CERTIFICATE_LEVELS.map((v) => ({ value: v, label: v }))}
              />
            </Form.Item>
            <Form.Item name="internal_model" label="内部型号">
              <Input style={{ width: 160 }} />
            </Form.Item>
          </Space>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="product_name" label="产品名称">
              <Input style={{ width: 220 }} />
            </Form.Item>
            <Form.Item name="category" label="类目">
              <Input style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="power" label="功率">
              <Input style={{ width: 140 }} />
            </Form.Item>
          </Space>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="price_rmb" label="人民币价">
              <InputNumber min={0} precision={2} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="price_usd" label="美元价">
              <InputNumber min={0} precision={2} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="unit_price" label="单价">
              <InputNumber min={0} precision={2} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="min_price" label="最低价">
              <InputNumber min={0} precision={2} style={{ width: 140 }} />
            </Form.Item>
          </Space>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="validity_days" label="有效期(天)" initialValue={30}>
              <InputNumber min={0} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="source_inquiry_no" label="来源询价号">
              <Input style={{ width: 200 }} />
            </Form.Item>
          </Space>
          <Form.Item name="configuration" label="配置">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="specs" label="规格">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
