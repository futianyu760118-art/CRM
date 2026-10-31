'use client';

import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App,
  Button,
  Drawer,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { api, buildQuery } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import type { PageResult } from '@/types';
import type { Lead } from '@/types/business';

interface UserOption {
  id: string;
  name: string;
  username: string;
  department_name: string | null;
}

export default function LeadsPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState<string | undefined>();
  const [createOpen, setCreateOpen] = useState(false);
  const [assignTarget, setAssignTarget] = useState<Lead | null>(null);
  const [form] = Form.useForm();
  const [assignForm] = Form.useForm<{ owner_id: string }>();

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['leads', page, keyword, status],
    queryFn: () =>
      api.get<PageResult<Lead>>(`/leads${buildQuery({ page, page_size: 10, keyword, status })}`),
  });

  const { data: users } = useQuery({
    queryKey: ['user-options'],
    queryFn: () => api.get<UserOption[]>('/users/options'),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['leads'] });

  const createMutation = useMutation({
    mutationFn: (values: Partial<Lead>) => api.post('/leads', values),
    onSuccess: () => {
      message.success('线索创建成功');
      setCreateOpen(false);
      form.resetFields();
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const assignMutation = useMutation({
    mutationFn: ({ id, ownerId }: { id: string; ownerId: string }) =>
      api.post(`/leads/${id}/assign`, { owner_id: ownerId }),
    onSuccess: () => {
      message.success('线索已分配');
      setAssignTarget(null);
      assignForm.resetFields();
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const convertMutation = useMutation({
    mutationFn: (id: string) => api.post(`/leads/${id}/convert`, { customer_level: 'B' }),
    onSuccess: (data) => {
      const result = data as { company_code: string };
      message.success(`已转为客户 ${result.company_code}`);
      queryClient.invalidateQueries({ queryKey: ['customers'] });
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const columns: ColumnsType<Lead> = [
    { title: '线索编号', dataIndex: 'lead_no', width: 160 },
    { title: '公司名称', dataIndex: 'name', ellipsis: true },
    { title: '联系人', dataIndex: 'contact_name', width: 120, render: (v) => v ?? '-' },
    { title: '邮箱', dataIndex: 'email', width: 200, render: (v) => v ?? '-' },
    { title: '国家', dataIndex: 'country', width: 100, render: (v) => v ?? '-' },
    { title: '来源', dataIndex: 'source', width: 120 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: string) => <StatusTag value={v} />,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: '操作',
      width: 200,
      fixed: 'right',
      render: (_, row) => (
        <Space size={4}>
          <HasPermission permission="lead:assign">
            <Button
              size="small"
              disabled={row.status === 'CONVERTED'}
              onClick={() => {
                setAssignTarget(row);
                assignForm.setFieldsValue({ owner_id: row.owner_id ?? '' });
              }}
            >
              分配
            </Button>
          </HasPermission>
          <HasPermission permission="lead:convert">
            <Button
              size="small"
              type="primary"
              ghost
              loading={convertMutation.isPending}
              disabled={row.status === 'CONVERTED' || row.status === 'INVALID'}
              onClick={() => convertMutation.mutate(row.id)}
            >
              {row.status === 'CONVERTED' ? '已转化' : '转客户'}
            </Button>
          </HasPermission>
        </Space>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="线索管理"
        description="外部获客入口：创建 → 分配 → 转客户（对应 F-02 ~ F-04）"
        extra={
          <Space>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="公司/联系人/邮箱"
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
              options={[
                { value: 'NEW', label: '新建' },
                { value: 'ASSIGNED', label: '已分配' },
                { value: 'CONVERTED', label: '已转化' },
                { value: 'INVALID', label: '无效' },
              ]}
            />
            <Button icon={<ReloadOutlined />} onClick={() => refetch()} />
            <HasPermission permission="lead:create">
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
                新建线索
              </Button>
            </HasPermission>
          </Space>
        }
      />

      <Table<Lead>
        rowKey="id"
        size="small"
        loading={isFetching}
        columns={columns}
        dataSource={data?.items ?? []}
        scroll={{ x: 1200 }}
        pagination={{
          current: data?.page ?? 1,
          pageSize: data?.page_size ?? 10,
          total: data?.total ?? 0,
          onChange: setPage,
        }}
      />

      <Modal
        title="新建线索"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending}
        destroyOnClose
      >
        <Form form={form} layout="vertical" requiredMark={false} onFinish={(v) => createMutation.mutate(v)}>
          <Form.Item name="name" label="公司名称" rules={[{ required: true }]}>
            <Input placeholder="客户公司名称" />
          </Form.Item>
          <Form.Item name="contact_name" label="联系人">
            <Input />
          </Form.Item>
          <Form.Item name="email" label="邮箱">
            <Input />
          </Form.Item>
          <Form.Item name="phone" label="电话">
            <Input />
          </Form.Item>
          <Form.Item name="country" label="国家">
            <Input />
          </Form.Item>
          <Form.Item name="source" label="来源" initialValue="EXHIBITION">
            <Select
              options={[
                { value: 'EXHIBITION', label: '展会' },
                { value: 'YUNQUTONG', label: '云渠通' },
                { value: 'WEBSITE', label: '官网' },
                { value: 'OUTBOUND', label: '主动开发' },
              ]}
            />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={`分配线索 ${assignTarget?.lead_no ?? ''}`}
        open={!!assignTarget}
        onClose={() => setAssignTarget(null)}
        width={420}
      >
        <Typography.Paragraph type="secondary">{assignTarget?.name}</Typography.Paragraph>
        <Form
          form={assignForm}
          layout="vertical"
          onFinish={(v) => assignTarget && assignMutation.mutate({ id: assignTarget.id, ownerId: v.owner_id })}
        >
          <Form.Item name="owner_id" label="负责人" rules={[{ required: true, message: '请选择负责人' }]}>
            <Select
              placeholder="选择业务员"
              options={(users ?? []).map((u) => ({
                value: u.id,
                label: `${u.name}（${u.department_name ?? '未分配部门'}）`,
              }))}
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={assignMutation.isPending} block>
            确认分配
          </Button>
        </Form>
      </Drawer>
    </>
  );
}
