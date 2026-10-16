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
import type { OrderStats, SalesOrder } from '@/types/sales';

const ORDER_STATUS_LABELS: Record<string, string> = {
  open: '未确认',
  confirmed: '已确认',
  procurement_ready: '待采购',
  material_ready: '物料齐备',
  packaging_done: '包装完成',
  shipped: '已发货',
  completed: '已完成',
  closed: '已关闭',
  cancelled: '已取消',
};

const RISK_LABELS: Record<string, { color: string; label: string }> = {
  blue: { color: 'blue', label: '蓝' },
  yellow: { color: 'gold', label: '黄' },
  red: { color: 'red', label: '红' },
  low: { color: 'green', label: '低' },
  medium: { color: 'orange', label: '中' },
  high: { color: 'red', label: '高' },
};

interface FormValues {
  order_no: string;
  line_no?: string;
  customer_name?: string;
  customer_code?: string;
  product_code?: string;
  product_name?: string;
  project_no?: string;
  quantity?: number;
  completed_qty?: number;
  order_amount?: number;
  risk_level?: string;
  promised_date?: dayjs.Dayjs | null;
  plan_date?: dayjs.Dayjs | null;
  online_date?: dayjs.Dayjs | null;
  remark?: string;
}

function toPayload(values: FormValues) {
  return {
    ...values,
    promised_date: values.promised_date?.format('YYYY-MM-DD') ?? null,
    plan_date: values.plan_date?.format('YYYY-MM-DD') ?? null,
    online_date: values.online_date?.format('YYYY-MM-DD') ?? null,
  };
}

export default function OrdersPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState<string | undefined>();
  const [risk, setRisk] = useState<string | undefined>();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<SalesOrder | null>(null);
  const [statusTarget, setStatusTarget] = useState<SalesOrder | null>(null);
  const [form] = Form.useForm<FormValues>();
  const [statusForm] = Form.useForm<{ status: string; reason?: string }>();

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['orders', page, keyword, status, risk],
    queryFn: () =>
      api.get<PageResult<SalesOrder>>(
        `/orders${buildQuery({ page, page_size: 10, keyword, status, risk_level: risk })}`,
      ),
  });

  const { data: stats } = useQuery({
    queryKey: ['order-stats'],
    queryFn: () => api.get<OrderStats>('/orders/stats'),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['orders'] });
  const invalidateStats = () => queryClient.invalidateQueries({ queryKey: ['order-stats'] });

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (row: SalesOrder) => {
    setEditing(row);
    form.setFieldsValue({
      order_no: row.order_no,
      line_no: row.line_no,
      customer_name: row.customer_name ?? undefined,
      customer_code: row.customer_code ?? undefined,
      product_code: row.product_code ?? undefined,
      product_name: row.product_name ?? undefined,
      project_no: row.project_no ?? undefined,
      quantity: row.quantity,
      completed_qty: row.completed_qty,
      order_amount: row.order_amount,
      risk_level: row.risk_level,
      promised_date: row.promised_date ? dayjs(row.promised_date) : null,
      plan_date: row.plan_date ? dayjs(row.plan_date) : null,
      online_date: row.online_date ? dayjs(row.online_date) : null,
      remark: row.remark ?? undefined,
    });
    setModalOpen(true);
  };

  const saveMutation = useMutation({
    mutationFn: (values: FormValues) => {
      const payload = toPayload(values);
      return editing
        ? api.put(`/orders/${editing.id}`, payload)
        : api.post('/orders', payload);
    },
    onSuccess: () => {
      message.success(editing ? '订单已更新' : '订单已创建');
      setModalOpen(false);
      invalidate();
      invalidateStats();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const statusMutation = useMutation({
    mutationFn: (values: { status: string; reason?: string }) =>
      api.post(`/orders/${statusTarget!.id}/status`, values),
    onSuccess: () => {
      message.success('订单状态已更新');
      setStatusTarget(null);
      invalidate();
      invalidateStats();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/orders/${id}`),
    onSuccess: () => {
      message.success('订单已删除');
      invalidate();
      invalidateStats();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const columns: ColumnsType<SalesOrder> = [
    { title: '订单号', dataIndex: 'order_no', width: 130, fixed: 'left' },
    { title: '行号', dataIndex: 'line_no', width: 70, render: (v: string) => v || '-' },
    { title: '客户', dataIndex: 'customer_name', ellipsis: true, render: (v) => v ?? '-' },
    { title: '产品', dataIndex: 'product_name', ellipsis: true, render: (v) => v ?? '-' },
    { title: '项目号', dataIndex: 'project_no', width: 110, render: (v) => v ?? '-' },
    { title: '数量', dataIndex: 'quantity', width: 90, render: (v) => formatNumber(v) },
    { title: '完成数', dataIndex: 'completed_qty', width: 90, render: (v) => formatNumber(v) },
    { title: '金额', dataIndex: 'order_amount', width: 110, render: (v) => formatNumber(v, 2) },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (v: string) => <StatusTag value={v} label={ORDER_STATUS_LABELS[v] ?? v} />,
    },
    {
      title: '风险',
      dataIndex: 'risk_level',
      width: 80,
      render: (v: string) => <Tag color={RISK_LABELS[v]?.color}>{RISK_LABELS[v]?.label ?? v}</Tag>,
    },
    { title: '交期', dataIndex: 'promised_date', width: 110, render: (v) => formatDate(v) },
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
          <HasPermission permission="order:status">
            <Button type="link" size="small" onClick={() => setStatusTarget(row)}>
              流转
            </Button>
          </HasPermission>
          <HasPermission permission="order:update">
            <Button type="link" size="small" onClick={() => openEdit(row)}>
              编辑
            </Button>
          </HasPermission>
          <HasPermission permission="order:delete">
            <Popconfirm title="确认删除该订单？" onConfirm={() => deleteMutation.mutate(row.id)}>
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
        title="订单管理"
        description="订单行录入 / 状态流转 / 风险跟踪（AC-M4）"
        extra={
          <Space wrap>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="订单号/客户/产品/项目号"
              style={{ width: 220 }}
              onPressEnter={(e) => {
                setPage(1);
                setKeyword((e.target as HTMLInputElement).value);
              }}
            />
            <Select
              allowClear
              placeholder="状态"
              style={{ width: 130 }}
              value={status}
              onChange={(v) => {
                setPage(1);
                setStatus(v);
              }}
              options={Object.entries(ORDER_STATUS_LABELS).map(([value, label]) => ({ value, label }))}
            />
            <Select
              allowClear
              placeholder="风险"
              style={{ width: 110 }}
              value={risk}
              onChange={(v) => {
                setPage(1);
                setRisk(v);
              }}
              options={Object.entries(RISK_LABELS).map(([value, r]) => ({ value, label: r.label }))}
            />
            <Button icon={<ReloadOutlined />} onClick={() => refetch()} />
            <HasPermission permission="order:create">
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                新建订单
              </Button>
            </HasPermission>
          </Space>
        }
      />

      {stats ? (
        <Space wrap style={{ marginBottom: 12 }}>
          <Tag color="geekblue">共 {data?.total ?? 0} 条</Tag>
          {Object.entries(stats.by_status).map(([s, n]) => (
            <Tag key={s}>{ORDER_STATUS_LABELS[s] ?? s} {n}</Tag>
          ))}
          {Object.entries(stats.by_risk).map(([r, n]) => (
            <Tag key={r} color={RISK_LABELS[r]?.color}>
              {RISK_LABELS[r]?.label ?? r} {n}
            </Tag>
          ))}
        </Space>
      ) : null}

      <Table<SalesOrder>
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
        title={editing ? '编辑订单' : '新建订单'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={saveMutation.isPending}
        destroyOnClose
        width={720}
      >
        <Form form={form} layout="vertical" requiredMark={false} onFinish={(v) => saveMutation.mutate(v)}>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="order_no" label="订单号" rules={[{ required: true }]}>
              <Input disabled={!!editing} placeholder="如 SO-20261016-001" style={{ width: 220 }} />
            </Form.Item>
            <Form.Item name="line_no" label="行号">
              <Input placeholder="如 10" style={{ width: 120 }} />
            </Form.Item>
            <Form.Item name="risk_level" label="风险等级" initialValue="low">
              <Select
                style={{ width: 120 }}
                options={Object.entries(RISK_LABELS).map(([value, r]) => ({ value, label: r.label }))}
              />
            </Form.Item>
          </Space>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="customer_name" label="客户名称">
              <Input style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="customer_code" label="客户编码">
              <Input style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="project_no" label="项目号">
              <Input style={{ width: 160 }} />
            </Form.Item>
          </Space>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="product_name" label="产品名称">
              <Input style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="product_code" label="产品编码">
              <Input style={{ width: 160 }} />
            </Form.Item>
          </Space>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="quantity" label="数量" initialValue={0}>
              <InputNumber min={0} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="completed_qty" label="已完成数量" initialValue={0}>
              <InputNumber min={0} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="order_amount" label="订单金额" initialValue={0}>
              <InputNumber min={0} precision={2} style={{ width: 140 }} />
            </Form.Item>
          </Space>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="promised_date" label="承诺交期">
              <DatePicker style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="plan_date" label="计划日期">
              <DatePicker style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="online_date" label="上线日期">
              <DatePicker style={{ width: 160 }} />
            </Form.Item>
          </Space>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={statusTarget ? `订单状态流转（${statusTarget.order_no}）` : '订单状态流转'}
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
              options={Object.entries(ORDER_STATUS_LABELS).map(([value, label]) => ({ value, label }))}
            />
          </Form.Item>
          <Form.Item name="reason" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
