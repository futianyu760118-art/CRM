'use client';

import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, DatePicker, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { api, buildQuery } from '@/lib/api';
import { formatDate, formatDateTime, formatNumber } from '@/lib/format';
import type { PageResult } from '@/types';
import type { Sample, SampleStats } from '@/types/sales';

const SAMPLE_STATUS_LABELS: Record<string, string> = {
  pending: '待确认',
  confirmed: '已确认',
  producing: '生产中',
  sent: '已寄出',
  customer_confirmed: '客户已确认',
  completed: '已完成',
};

const SAMPLE_TYPES = ['常规', '新品', '改良', '急样'];

interface FormValues {
  sample_no?: string;
  customer_name: string;
  inquiry_no?: string;
  product_name?: string;
  product_code?: string;
  quantity?: number;
  sample_type?: string;
  send_date?: dayjs.Dayjs | null;
  confirm_date?: dayjs.Dayjs | null;
  remark?: string;
}

function toPayload(values: FormValues) {
  return {
    ...values,
    send_date: values.send_date?.format('YYYY-MM-DD') ?? null,
    confirm_date: values.confirm_date?.format('YYYY-MM-DD') ?? null,
  };
}

export default function SamplesPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState<string | undefined>();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Sample | null>(null);
  const [statusTarget, setStatusTarget] = useState<Sample | null>(null);
  const [form] = Form.useForm<FormValues>();
  const [statusForm] = Form.useForm<{ status: string }>();

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['samples', page, keyword, status],
    queryFn: () =>
      api.get<PageResult<Sample>>(`/samples${buildQuery({ page, page_size: 10, keyword, status })}`),
  });

  const { data: stats } = useQuery({
    queryKey: ['sample-stats'],
    queryFn: () => api.get<SampleStats>('/samples/stats'),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['samples'] });
  const invalidateStats = () => queryClient.invalidateQueries({ queryKey: ['sample-stats'] });

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (row: Sample) => {
    setEditing(row);
    form.setFieldsValue({
      sample_no: row.sample_no,
      customer_name: row.customer_name,
      inquiry_no: row.inquiry_no ?? undefined,
      product_name: row.product_name ?? undefined,
      product_code: row.product_code ?? undefined,
      quantity: row.quantity,
      sample_type: row.sample_type,
      send_date: row.send_date ? dayjs(row.send_date) : null,
      confirm_date: row.confirm_date ? dayjs(row.confirm_date) : null,
      remark: row.remark ?? undefined,
    });
    setModalOpen(true);
  };

  const saveMutation = useMutation({
    mutationFn: (values: FormValues) => {
      const payload = toPayload(values);
      return editing
        ? api.put(`/samples/${editing.id}`, payload)
        : api.post('/samples', payload);
    },
    onSuccess: () => {
      message.success(editing ? '样品已更新' : '样品已创建');
      setModalOpen(false);
      invalidate();
      invalidateStats();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const statusMutation = useMutation({
    mutationFn: (values: { status: string }) => api.post(`/samples/${statusTarget!.id}/status`, values),
    onSuccess: () => {
      message.success('样品状态已更新');
      setStatusTarget(null);
      invalidate();
      invalidateStats();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/samples/${id}`),
    onSuccess: () => {
      message.success('样品已删除');
      invalidate();
      invalidateStats();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const columns: ColumnsType<Sample> = [
    { title: '样品号', dataIndex: 'sample_no', width: 140, fixed: 'left' },
    { title: '客户', dataIndex: 'customer_name', ellipsis: true },
    { title: '询价号', dataIndex: 'inquiry_no', width: 130, render: (v) => v ?? '-' },
    { title: '产品', dataIndex: 'product_name', ellipsis: true, render: (v) => v ?? '-' },
    { title: '数量', dataIndex: 'quantity', width: 80, render: (v) => formatNumber(v) },
    { title: '样品类型', dataIndex: 'sample_type', width: 100 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 120,
      render: (v: string) => <StatusTag value={v} label={SAMPLE_STATUS_LABELS[v] ?? v} />,
    },
    { title: '寄出日期', dataIndex: 'send_date', width: 110, render: (v) => formatDate(v) },
    { title: '确认日期', dataIndex: 'confirm_date', width: 110, render: (v) => formatDate(v) },
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
      width: 180,
      fixed: 'right',
      render: (_, row) => (
        <Space size={0}>
          <HasPermission permission="sample:status">
            <Button type="link" size="small" onClick={() => setStatusTarget(row)}>
              流转
            </Button>
          </HasPermission>
          <HasPermission permission="sample:update">
            <Button type="link" size="small" onClick={() => openEdit(row)}>
              编辑
            </Button>
          </HasPermission>
          <HasPermission permission="sample:delete">
            <Popconfirm title="确认删除该样品？" onConfirm={() => deleteMutation.mutate(row.id)}>
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
        title="样品管理"
        description="样品登记 / 寄送确认 / 状态推进（AC-M5）"
        extra={
          <Space wrap>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="样品号/客户/产品/询价号"
              style={{ width: 220 }}
              onPressEnter={(e) => {
                setPage(1);
                setKeyword((e.target as HTMLInputElement).value);
              }}
            />
            <Select
              allowClear
              placeholder="状态"
              style={{ width: 140 }}
              value={status}
              onChange={(v) => {
                setPage(1);
                setStatus(v);
              }}
              options={Object.entries(SAMPLE_STATUS_LABELS).map(([value, label]) => ({ value, label }))}
            />
            <Button icon={<ReloadOutlined />} onClick={() => refetch()} />
            <HasPermission permission="sample:create">
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                新建样品
              </Button>
            </HasPermission>
          </Space>
        }
      />

      {stats ? (
        <Space wrap style={{ marginBottom: 12 }}>
          <Tag color="geekblue">共 {data?.total ?? 0} 条</Tag>
          {Object.entries(stats.by_status).map(([s, n]) => (
            <Tag key={s}>{SAMPLE_STATUS_LABELS[s] ?? s} {n}</Tag>
          ))}
        </Space>
      ) : null}

      <Table<Sample>
        rowKey="id"
        size="small"
        loading={isFetching}
        columns={columns}
        dataSource={data?.items ?? []}
        scroll={{ x: 1400 }}
        pagination={{
          current: data?.page ?? 1,
          pageSize: data?.page_size ?? 10,
          total: data?.total ?? 0,
          onChange: setPage,
        }}
      />

      <Modal
        title={editing ? '编辑样品' : '新建样品'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={saveMutation.isPending}
        destroyOnClose
        width={640}
      >
        <Form form={form} layout="vertical" requiredMark={false} onFinish={(v) => saveMutation.mutate(v)}>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="sample_no" label="样品号（留空自动生成）">
              <Input disabled={!!editing} placeholder="如 SMP-0001" style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="sample_type" label="样品类型" initialValue="常规">
              <Select style={{ width: 140 }} options={SAMPLE_TYPES.map((v) => ({ value: v, label: v }))} />
            </Form.Item>
          </Space>
          <Form.Item name="customer_name" label="客户名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="inquiry_no" label="关联询价号">
              <Input style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="quantity" label="数量" initialValue={0}>
              <InputNumber min={0} style={{ width: 140 }} />
            </Form.Item>
          </Space>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="product_name" label="产品名称">
              <Input style={{ width: 220 }} />
            </Form.Item>
            <Form.Item name="product_code" label="产品编码">
              <Input style={{ width: 160 }} />
            </Form.Item>
          </Space>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="send_date" label="寄出日期">
              <DatePicker style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="confirm_date" label="客户确认日期">
              <DatePicker style={{ width: 160 }} />
            </Form.Item>
          </Space>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={statusTarget ? `样品状态流转（${statusTarget.sample_no}）` : '样品状态流转'}
        open={!!statusTarget}
        onCancel={() => setStatusTarget(null)}
        onOk={() => statusForm.submit()}
        confirmLoading={statusMutation.isPending}
        destroyOnClose
      >
        <Form
          form={statusForm}
          layout="vertical"
          initialValues={{ status: statusTarget?.status }}
          onFinish={(v) => statusMutation.mutate(v)}
        >
          <Form.Item name="status" label="目标状态" rules={[{ required: true }]}>
            <Select
              options={Object.entries(SAMPLE_STATUS_LABELS).map(([value, label]) => ({ value, label }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
