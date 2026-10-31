'use client';

import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  App,
  Button,
  DatePicker,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Progress,
  Select,
  Space,
  Switch,
  Table,
  Tag,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs, { type Dayjs } from 'dayjs';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { api, buildQuery } from '@/lib/api';
import {
  COURIER_OPTIONS,
  COURIERS,
  SAMPLE_NEXT_STATUS,
  SAMPLE_STATUS_LABELS,
  SAMPLE_STATUS_OPTIONS,
} from '@/lib/dictionaries';
import { formatDate, formatDateTime } from '@/lib/format';
import type { PageResult } from '@/types';
import type { Sample, SampleStats } from '@/types/sales';

const SAMPLE_TYPES = ['常规', '新品', '改良', '急样'];
const STATUS_ORDER = ['pending', 'producing', 'testing', 'sent', 'feedback'];

interface UserOption {
  id: string;
  name: string;
  username: string;
}

interface FormValues {
  sample_no?: string;
  customer_name: string;
  inquiry_no?: string;
  product_name?: string;
  product_code?: string;
  product_model: string;
  quantity: number;
  sample_type: string;
  sample_requirement?: string;
  plan_date?: Dayjs | null;
  owner_id?: string;
  remark?: string;
}

interface StatusFormValues {
  courier?: string;
  tracking_no?: string;
  send_date?: Dayjs | null;
  feedback?: string;
  feedback_date?: Dayjs | null;
}

function toPayload(values: FormValues) {
  return {
    ...values,
    plan_date: values.plan_date?.format('YYYY-MM-DD') ?? null,
  };
}

export default function SamplesPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState<string | undefined>();
  const [ownerId, setOwnerId] = useState<string | undefined>();
  const [planRange, setPlanRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Sample | null>(null);
  const [statusTarget, setStatusTarget] = useState<Sample | null>(null);
  const [form] = Form.useForm<FormValues>();
  const [statusForm] = Form.useForm<StatusFormValues>();

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['samples', page, keyword, status, ownerId, planRange?.[0]?.valueOf(), planRange?.[1]?.valueOf(), overdueOnly],
    queryFn: () =>
      api.get<PageResult<Sample>>(
        `/samples${buildQuery({
          page,
          page_size: 10,
          keyword,
          status,
          owner_id: ownerId,
          plan_date_from: planRange?.[0]?.format('YYYY-MM-DD'),
          plan_date_to: planRange?.[1]?.format('YYYY-MM-DD'),
          overdue: overdueOnly ? true : undefined,
        })}`,
      ),
  });

  const { data: stats } = useQuery({
    queryKey: ['sample-stats'],
    queryFn: () => api.get<SampleStats>('/samples/stats'),
  });

  const { data: users } = useQuery({
    queryKey: ['user-options'],
    queryFn: () => api.get<UserOption[]>('/users/options'),
  });

  const ownerName = (id: string | null | undefined) =>
    id ? (users?.find((u) => u.id === id)?.name ?? id.slice(0, 8)) : '-';

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['samples'] });
    queryClient.invalidateQueries({ queryKey: ['sample-stats'] });
  };

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ plan_date: dayjs().add(7, 'day') });
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
      product_model: row.product_model ?? undefined,
      quantity: row.quantity,
      sample_type: row.sample_type,
      sample_requirement: row.sample_requirement ?? undefined,
      plan_date: row.plan_date ? dayjs(row.plan_date) : null,
      owner_id: row.owner_id ?? undefined,
      remark: row.remark ?? undefined,
    });
    setModalOpen(true);
  };

  const openStatus = (row: Sample) => {
    statusForm.resetFields();
    setStatusTarget(row);
  };

  const saveMutation = useMutation({
    mutationFn: (values: FormValues) => {
      const payload = toPayload(values);
      return editing ? api.put(`/samples/${editing.id}`, payload) : api.post('/samples', payload);
    },
    onSuccess: () => {
      message.success(editing ? '样品已更新' : '样品已创建');
      setModalOpen(false);
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const statusMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.post(`/samples/${statusTarget!.id}/status`, payload),
    onSuccess: () => {
      message.success('样品状态已更新');
      setStatusTarget(null);
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/samples/${id}`),
    onSuccess: () => {
      message.success('样品已删除');
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const nextStatus = statusTarget ? SAMPLE_NEXT_STATUS[statusTarget.status] : undefined;

  const submitStatus = async () => {
    if (!statusTarget || !nextStatus) return;
    const values = (await statusForm.validateFields().catch(() => null)) as StatusFormValues | null;
    if (!values) return;
    const payload: Record<string, unknown> = { status: nextStatus };
    if (nextStatus === 'sent') {
      payload.courier = values.courier;
      payload.tracking_no = values.tracking_no;
      payload.send_date = values.send_date?.format('YYYY-MM-DD');
    }
    if (nextStatus === 'feedback') {
      payload.feedback = values.feedback;
      payload.feedback_date = values.feedback_date?.format('YYYY-MM-DD');
    }
    statusMutation.mutate(payload);
  };

  const columns: ColumnsType<Sample> = [
    { title: '样品号', dataIndex: 'sample_no', width: 140, fixed: 'left' },
    { title: '客户', dataIndex: 'customer_name', ellipsis: true },
    { title: '产品型号', dataIndex: 'product_model', width: 150, ellipsis: true, render: (v) => v ?? '-' },
    { title: '产品名称', dataIndex: 'product_name', ellipsis: true, render: (v) => v ?? '-' },
    { title: '数量', dataIndex: 'quantity', width: 80, render: (v: number) => v ?? '-' },
    {
      title: '样品要求',
      dataIndex: 'sample_requirement',
      ellipsis: true,
      render: (v) => v ?? '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 170,
      render: (v: string) => (
        <Space size={4} wrap>
          <StatusTag value={v} label={SAMPLE_STATUS_LABELS[v] ?? v} />
          <Progress
            size="small"
            style={{ width: 70, margin: 0 }}
            percent={((STATUS_ORDER.indexOf(v) + 1) / STATUS_ORDER.length) * 100}
            showInfo={false}
          />
        </Space>
      ),
    },
    {
      title: '计划完成',
      dataIndex: 'plan_date',
      width: 150,
      render: (v: string | null, row) => (
        <Space size={4} wrap>
          <span>{formatDate(v)}</span>
          {row.overdue_days != null ? <Tag color="red">逾期{row.overdue_days}天</Tag> : null}
        </Space>
      ),
    },
    {
      title: '快递',
      dataIndex: 'tracking_no',
      width: 170,
      render: (v: string | null, row) =>
        v ? (
          <span>
            {row.courier ? COURIERS[row.courier] ?? row.courier : '-'} {v}
          </span>
        ) : (
          '-'
        ),
    },
    {
      title: '负责人',
      dataIndex: 'owner_id',
      width: 110,
      render: (v: string | null) => ownerName(v),
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
            <Button
              type="link"
              size="small"
              disabled={!SAMPLE_NEXT_STATUS[row.status]}
              onClick={() => openStatus(row)}
            >
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
        description="样品登记 / 进度流转（待确认→制作中→测试中→已寄出→客户反馈）"
        extra={
          <Space wrap>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="样品号/客户/型号/询价号"
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
              options={SAMPLE_STATUS_OPTIONS}
            />
            <Select
              allowClear
              placeholder="负责人"
              style={{ width: 140 }}
              value={ownerId}
              onChange={(v) => {
                setPage(1);
                setOwnerId(v);
              }}
              options={(users ?? []).map((u) => ({ value: u.id, label: u.name }))}
            />
            <DatePicker.RangePicker
              value={planRange}
              onChange={(v) => {
                setPage(1);
                setPlanRange(v as [Dayjs, Dayjs] | null);
              }}
              placeholder={['计划从', '计划至']}
              style={{ width: 240 }}
            />
            <Space size={4}>
              <Switch size="small" checked={overdueOnly} onChange={(v) => { setPage(1); setOverdueOnly(v); }} />
              <span>仅看逾期</span>
            </Space>
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
          {SAMPLE_STATUS_OPTIONS.map((o) => (
            <Tag key={o.value}>
              {o.label} {stats.by_status[o.value] ?? 0}
            </Tag>
          ))}
          {stats.overdue > 0 ? <Tag color="red">逾期 {stats.overdue}</Tag> : null}
        </Space>
      ) : null}

      <Table<Sample>
        rowKey="id"
        size="small"
        loading={isFetching}
        columns={columns}
        dataSource={data?.items ?? []}
        scroll={{ x: 1600 }}
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
        width={720}
      >
        <Form form={form} layout="vertical" requiredMark={false} onFinish={(v) => saveMutation.mutate(v)}>
          <Space style={{ display: 'flex' }} align="start" wrap>
            <Form.Item name="sample_no" label="样品号（留空自动生成）">
              <Input disabled={!!editing} placeholder="如 SMP-0001" style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="sample_type" label="样品类型" initialValue="常规">
              <Select style={{ width: 140 }} options={SAMPLE_TYPES.map((v) => ({ value: v, label: v }))} />
            </Form.Item>
            <Form.Item name="owner_id" label="负责人">
              <Select
                allowClear
                placeholder="默认本人"
                style={{ width: 160 }}
                options={(users ?? []).map((u) => ({ value: u.id, label: u.name }))}
              />
            </Form.Item>
          </Space>
          <Form.Item name="customer_name" label="客户名称" rules={[{ required: true, message: '请填写客户名称' }]}>
            <Input />
          </Form.Item>
          <Space style={{ display: 'flex' }} align="start" wrap>
            <Form.Item name="inquiry_no" label="关联询价号">
              <Input style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="product_model" label="产品型号" rules={[{ required: true, message: '请填写产品型号' }]}>
              <Input style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="quantity" label="数量" initialValue={1} rules={[{ required: true, message: '请填写数量' }]}>
              <InputNumber min={0.01} precision={2} style={{ width: 140 }} />
            </Form.Item>
          </Space>
          <Space style={{ display: 'flex' }} align="start" wrap>
            <Form.Item name="product_name" label="产品名称">
              <Input style={{ width: 220 }} />
            </Form.Item>
            <Form.Item name="product_code" label="产品编码">
              <Input style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="plan_date" label="计划完成日期">
              <DatePicker style={{ width: 160 }} />
            </Form.Item>
          </Space>
          <Form.Item name="sample_requirement" label="样品要求">
            <Input.TextArea rows={2} maxLength={2000} placeholder="外观/参数/包装等要求" />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={statusTarget ? `样品流转（${statusTarget.sample_no}）` : '样品流转'}
        open={!!statusTarget}
        onCancel={() => setStatusTarget(null)}
        onOk={submitStatus}
        confirmLoading={statusMutation.isPending}
        okButtonProps={{ disabled: !nextStatus }}
        destroyOnClose
        width={560}
      >
        {statusTarget ? (
          <>
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message={`当前状态：${SAMPLE_STATUS_LABELS[statusTarget.status] ?? statusTarget.status}${
                nextStatus ? `，下一状态：${SAMPLE_STATUS_LABELS[nextStatus]}` : '（终态，不可继续流转）'
              }`}
            />
            {!nextStatus ? (
              <Empty description="样品已处于【客户反馈】终态" />
            ) : (
              <Form form={statusForm} layout="vertical" preserve={false}>
                {nextStatus === 'sent' ? (
                  <>
                    <Space style={{ display: 'flex' }} align="start">
                      <Form.Item
                        name="courier"
                        label="快递公司"
                        rules={[{ required: true, message: '请选择快递公司' }]}
                      >
                        <Select style={{ width: 180 }} options={COURIER_OPTIONS} />
                      </Form.Item>
                      <Form.Item
                        name="tracking_no"
                        label="快递单号"
                        rules={[
                          { required: true, message: '请填写快递单号' },
                          { pattern: /^[A-Za-z0-9-]{6,40}$/, message: '应为 6–40 位字母、数字或连字符' },
                        ]}
                      >
                        <Input style={{ width: 220 }} />
                      </Form.Item>
                    </Space>
                    <Form.Item
                      name="send_date"
                      label="寄出日期"
                      initialValue={dayjs()}
                      rules={[{ required: true, message: '请选择寄出日期' }]}
                    >
                      <DatePicker style={{ width: 180 }} />
                    </Form.Item>
                  </>
                ) : null}
                {nextStatus === 'feedback' ? (
                  <>
                    <Form.Item
                      name="feedback"
                      label="客户反馈"
                      rules={[{ required: true, message: '请填写客户反馈' }]}
                    >
                      <Input.TextArea rows={3} maxLength={2000} />
                    </Form.Item>
                    <Form.Item
                      name="feedback_date"
                      label="反馈日期"
                      initialValue={dayjs()}
                      rules={[{ required: true, message: '请选择反馈日期' }]}
                    >
                      <DatePicker style={{ width: 180 }} />
                    </Form.Item>
                  </>
                ) : null}
              </Form>
            )}
          </>
        ) : null}
      </Modal>
    </>
  );
}
