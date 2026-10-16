'use client';

import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App,
  Button,
  Descriptions,
  Drawer,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Timeline,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { api, buildQuery } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import type { PageResult } from '@/types';
import type { Feedback, FeedbackStats } from '@/types/sales';

const FEEDBACK_TYPE_LABELS: Record<string, string> = {
  bug: '缺陷',
  feature: '新需求',
  improvement: '改进建议',
  question: '咨询',
};

const PRIORITY_LABELS: Record<string, { color: string; label: string }> = {
  low: { color: 'default', label: '低' },
  medium: { color: 'blue', label: '中' },
  high: { color: 'orange', label: '高' },
  urgent: { color: 'red', label: '紧急' },
};

const FEEDBACK_STATUS_LABELS: Record<string, string> = {
  open: '待处理',
  processing: '处理中',
  resolved: '已解决',
  closed: '已关闭',
};

const ACTION_LABELS: Record<string, string> = {
  submit: '提交',
  comment: '评论',
  status: '状态变更',
  assign: '指派',
  resolve: '解决',
  close: '关闭',
};

interface CreateValues {
  title: string;
  description?: string;
  type?: string;
  priority?: string;
  module?: string;
}

export default function FeedbackPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [type, setType] = useState<string | undefined>();
  const [priority, setPriority] = useState<string | undefined>();
  const [status, setStatus] = useState<string | undefined>();
  const [createOpen, setCreateOpen] = useState(false);
  const [detail, setDetail] = useState<Feedback | null>(null);
  const [statusTarget, setStatusTarget] = useState<Feedback | null>(null);
  const [assignTarget, setAssignTarget] = useState<Feedback | null>(null);
  const [createForm] = Form.useForm<CreateValues>();
  const [statusForm] = Form.useForm<{ status: string; resolution?: string; content?: string }>();
  const [assignForm] = Form.useForm<{ assignee: string }>();
  const [commentForm] = Form.useForm<{ content: string }>();

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['feedback', page, keyword, type, priority, status],
    queryFn: () =>
      api.get<PageResult<Feedback>>(
        `/feedback${buildQuery({ page, page_size: 10, keyword, type, priority, status })}`,
      ),
  });

  const { data: stats } = useQuery({
    queryKey: ['feedback-stats'],
    queryFn: () => api.get<FeedbackStats>('/feedback/stats'),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['feedback'] });
  const invalidateStats = () => queryClient.invalidateQueries({ queryKey: ['feedback-stats'] });

  const createMutation = useMutation({
    mutationFn: (values: CreateValues) => api.post('/feedback', values),
    onSuccess: (res) => {
      message.success('反馈已提交');
      setCreateOpen(false);
      createForm.resetFields();
      invalidate();
      invalidateStats();
      setDetail(res as Feedback);
    },
    onError: (e: Error) => message.error(e.message),
  });

  const statusMutation = useMutation({
    mutationFn: (values: { status: string; resolution?: string; content?: string }) =>
      api.post(`/feedback/${statusTarget!.id}/status`, values),
    onSuccess: (res) => {
      message.success('反馈状态已更新');
      setStatusTarget(null);
      invalidate();
      invalidateStats();
      setDetail(res as Feedback);
    },
    onError: (e: Error) => message.error(e.message),
  });

  const assignMutation = useMutation({
    mutationFn: (values: { assignee: string }) => api.post(`/feedback/${assignTarget!.id}/assign`, values),
    onSuccess: (res) => {
      message.success('已指派');
      setAssignTarget(null);
      invalidate();
      setDetail(res as Feedback);
    },
    onError: (e: Error) => message.error(e.message),
  });

  const commentMutation = useMutation({
    mutationFn: (values: { content: string }) => api.post(`/feedback/${detail!.id}/comments`, values),
    onSuccess: (res) => {
      message.success('评论已提交');
      commentForm.resetFields();
      invalidate();
      setDetail(res as Feedback);
    },
    onError: (e: Error) => message.error(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/feedback/${id}`),
    onSuccess: () => {
      message.success('反馈已删除');
      invalidate();
      invalidateStats();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const columns: ColumnsType<Feedback> = [
    { title: '反馈号', dataIndex: 'feedback_no', width: 130, fixed: 'left' },
    { title: '标题', dataIndex: 'title', ellipsis: true },
    {
      title: '类型',
      dataIndex: 'type',
      width: 90,
      render: (v: string) => FEEDBACK_TYPE_LABELS[v] ?? v,
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      width: 90,
      render: (v: string) => <Tag color={PRIORITY_LABELS[v]?.color}>{PRIORITY_LABELS[v]?.label ?? v}</Tag>,
    },
    { title: '模块', dataIndex: 'module', width: 110, render: (v) => v ?? '-' },
    { title: '提交人', dataIndex: 'submitter', width: 100, render: (v) => v ?? '-' },
    { title: '指派给', dataIndex: 'assignee', width: 100, render: (v) => v ?? '-' },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: string) => <StatusTag value={v} label={FEEDBACK_STATUS_LABELS[v] ?? v} />,
    },
    { title: '跟进', dataIndex: 'followup_count', width: 70 },
    { title: '创建时间', dataIndex: 'created_at', width: 160, render: (v) => formatDateTime(v) },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      fixed: 'right',
      render: (_, row) => (
        <Space size={0}>
          <Button type="link" size="small" onClick={() => setDetail(row)}>
            详情
          </Button>
          <HasPermission permission="feedback:handle">
            <Button type="link" size="small" onClick={() => setStatusTarget(row)}>
              流转
            </Button>
            <Button type="link" size="small" onClick={() => setAssignTarget(row)}>
              指派
            </Button>
          </HasPermission>
          <HasPermission permission="feedback:delete">
            <Popconfirm title="确认删除该反馈？" onConfirm={() => deleteMutation.mutate(row.id)}>
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
        title="问题反馈"
        description="问题 / 建议收集、指派与跟进处理（AC-M6）"
        extra={
          <Space wrap>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="反馈号/标题"
              style={{ width: 200 }}
              onPressEnter={(e) => {
                setPage(1);
                setKeyword((e.target as HTMLInputElement).value);
              }}
            />
            <Select
              allowClear
              placeholder="类型"
              style={{ width: 110 }}
              value={type}
              onChange={(v) => {
                setPage(1);
                setType(v);
              }}
              options={Object.entries(FEEDBACK_TYPE_LABELS).map(([value, label]) => ({ value, label }))}
            />
            <Select
              allowClear
              placeholder="优先级"
              style={{ width: 110 }}
              value={priority}
              onChange={(v) => {
                setPage(1);
                setPriority(v);
              }}
              options={Object.entries(PRIORITY_LABELS).map(([value, p]) => ({ value, label: p.label }))}
            />
            <Select
              allowClear
              placeholder="状态"
              style={{ width: 110 }}
              value={status}
              onChange={(v) => {
                setPage(1);
                setStatus(v);
              }}
              options={Object.entries(FEEDBACK_STATUS_LABELS).map(([value, label]) => ({ value, label }))}
            />
            <Button icon={<ReloadOutlined />} onClick={() => refetch()} />
            <HasPermission permission="feedback:create">
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
                提交反馈
              </Button>
            </HasPermission>
          </Space>
        }
      />

      {stats ? (
        <Space wrap style={{ marginBottom: 12 }}>
          <Tag color="geekblue">共 {data?.total ?? 0} 条</Tag>
          {Object.entries(stats.by_status).map(([s, n]) => (
            <Tag key={s}>{FEEDBACK_STATUS_LABELS[s] ?? s} {n}</Tag>
          ))}
          {Object.entries(stats.by_type).map(([t, n]) => (
            <Tag key={t} color="cyan">
              {FEEDBACK_TYPE_LABELS[t] ?? t} {n}
            </Tag>
          ))}
        </Space>
      ) : null}

      <Table<Feedback>
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
        title="提交反馈"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => createForm.submit()}
        confirmLoading={createMutation.isPending}
        destroyOnClose
      >
        <Form form={createForm} layout="vertical" requiredMark={false} onFinish={(v) => createMutation.mutate(v)}>
          <Form.Item name="title" label="标题" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="type" label="类型" initialValue="bug">
              <Select
                style={{ width: 140 }}
                options={Object.entries(FEEDBACK_TYPE_LABELS).map(([value, label]) => ({ value, label }))}
              />
            </Form.Item>
            <Form.Item name="priority" label="优先级" initialValue="medium">
              <Select
                style={{ width: 140 }}
                options={Object.entries(PRIORITY_LABELS).map(([value, p]) => ({ value, label: p.label }))}
              />
            </Form.Item>
            <Form.Item name="module" label="所属模块">
              <Input style={{ width: 160 }} placeholder="如 订单 / 样品" />
            </Form.Item>
          </Space>
          <Form.Item name="description" label="问题描述">
            <Input.TextArea rows={4} />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={detail ? `反馈详情（${detail.feedback_no}）` : '反馈详情'}
        open={!!detail}
        onClose={() => setDetail(null)}
        width={560}
      >
        {detail ? (
          <>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="标题">{detail.title}</Descriptions.Item>
              <Descriptions.Item label="类型">{FEEDBACK_TYPE_LABELS[detail.type] ?? detail.type}</Descriptions.Item>
              <Descriptions.Item label="优先级">
                {PRIORITY_LABELS[detail.priority]?.label ?? detail.priority}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                {FEEDBACK_STATUS_LABELS[detail.status] ?? detail.status}
              </Descriptions.Item>
              <Descriptions.Item label="提交人">{detail.submitter ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="指派给">{detail.assignee ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="模块">{detail.module ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="描述">{detail.description ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="解决方案">{detail.resolution ?? '-'}</Descriptions.Item>
            </Descriptions>

            <h4 style={{ marginTop: 16 }}>跟进记录</h4>
            <Timeline
              items={(detail.followups ?? []).map((f) => ({
                color: f.action === 'status' ? 'blue' : 'gray',
                children: (
                  <div>
                    <div>
                      <Tag>{ACTION_LABELS[f.action] ?? f.action}</Tag>
                      {f.operator ?? '-'}
                      {f.assignee ? ` → ${f.assignee}` : ''}
                    </div>
                    <div style={{ color: '#999', fontSize: 12 }}>{formatDateTime(f.created_at)}</div>
                    {f.content ? <div>{f.content}</div> : null}
                  </div>
                ),
              }))}
            />

            <HasPermission permission="feedback:handle">
              <Space.Compact style={{ width: '100%', marginTop: 16 }}>
                <Form
                  form={commentForm}
                  layout="inline"
                  style={{ display: 'flex', flex: 1 }}
                  onFinish={(v) => commentMutation.mutate(v)}
                >
                  <Form.Item name="content" rules={[{ required: true, message: '请输入评论' }]} style={{ flex: 1 }}>
                    <Input placeholder="添加跟进评论" />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" loading={commentMutation.isPending}>
                    评论
                  </Button>
                </Form>
              </Space.Compact>
            </HasPermission>
          </>
        ) : null}
      </Drawer>

      <Modal
        title={statusTarget ? `反馈状态流转（${statusTarget.feedback_no}）` : '反馈状态流转'}
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
              options={Object.entries(FEEDBACK_STATUS_LABELS).map(([value, label]) => ({ value, label }))}
            />
          </Form.Item>
          <Form.Item name="resolution" label="解决方案">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={assignTarget ? `反馈指派（${assignTarget.feedback_no}）` : '反馈指派'}
        open={!!assignTarget}
        onCancel={() => setAssignTarget(null)}
        onOk={() => assignForm.submit()}
        confirmLoading={assignMutation.isPending}
        destroyOnClose
      >
        <Form form={assignForm} layout="vertical" onFinish={(v) => assignMutation.mutate(v)}>
          <Form.Item name="assignee" label="指派给" rules={[{ required: true }]}>
            <Input placeholder="处理人姓名" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
