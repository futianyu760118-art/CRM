'use client';

import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Form, Input, Modal, Segmented, Select, Space, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { api, buildQuery } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import type { PageResult } from '@/types';
import type { TaskItem } from '@/types/business';

export default function TasksPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [scope, setScope] = useState<'mine' | 'all'>('mine');
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const query = useQuery({
    queryKey: ['tasks-page', scope],
    queryFn: () =>
      scope === 'mine'
        ? api.get<PageResult<TaskItem>>(`/tasks/mine${buildQuery({ page_size: 50 })}`)
        : api.get<PageResult<TaskItem>>(`/tasks${buildQuery({ page_size: 50 })}`),
  });

  const complete = useMutation({
    mutationFn: (id: string) => api.post(`/tasks/${id}/complete`),
    onSuccess: () => {
      message.success('任务已完成');
      queryClient.invalidateQueries({ queryKey: ['tasks-page'] });
    },
  });

  const create = useMutation({
    mutationFn: (values: Record<string, unknown>) => api.post('/tasks', values),
    onSuccess: () => {
      message.success('任务已创建');
      setOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['tasks-page'] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  const columns: ColumnsType<TaskItem> = [
    { title: '任务标题', dataIndex: 'title', ellipsis: true },
    {
      title: '优先级',
      dataIndex: 'priority',
      width: 90,
      render: (v: string) => <StatusTag value={v} />,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: string) => <StatusTag value={v} />,
    },
    {
      title: '截止时间',
      dataIndex: 'due_date',
      width: 180,
      render: (v: string | null) => formatDateTime(v),
    },
    { title: '关联业务', dataIndex: 'biz_type', width: 130, render: (v) => v ?? '-' },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 180,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: '操作',
      width: 100,
      render: (_, row) =>
        row.status === 'PENDING' ? (
          <HasPermission permission="task:update">
            <Button size="small" type="primary" ghost onClick={() => complete.mutate(row.id)}>
              完成
            </Button>
          </HasPermission>
        ) : (
          '-'
        ),
    },
  ];

  return (
    <>
      <PageHeader
        title="任务与跟进"
        description="我的任务 / 全部任务，支持完成操作（对应 F-19、F-20）"
        extra={
          <Space>
            <Segmented
              value={scope}
              onChange={(v) => setScope(v as 'mine' | 'all')}
              options={[
                { label: '我的任务', value: 'mine' },
                { label: '全部任务', value: 'all' },
              ]}
            />
            <Button icon={<ReloadOutlined />} onClick={() => query.refetch()} />
            <HasPermission permission="task:create">
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
                新建任务
              </Button>
            </HasPermission>
          </Space>
        }
      />

      <Table<TaskItem>
        rowKey="id"
        size="small"
        loading={query.isFetching}
        columns={columns}
        dataSource={query.data?.items ?? []}
        pagination={{ pageSize: 20 }}
      />

      <Modal
        title="新建任务"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={create.isPending}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={(v) => create.mutate(v)}>
          <Form.Item name="title" label="任务标题" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="content" label="说明">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="priority" label="优先级" initialValue="MEDIUM">
            <Select
              options={[
                { value: 'HIGH', label: '高' },
                { value: 'MEDIUM', label: '中' },
                { value: 'LOW', label: '低' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
