'use client';

import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Form, Input, Modal, Select, Space, Switch, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import { api, buildQuery } from '@/lib/api';
import type { PageResult } from '@/types';
import type { Company, Contact } from '@/types/business';

export default function ContactsPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [companyId, setCompanyId] = useState<string | undefined>();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['contacts', page, keyword, companyId],
    queryFn: () =>
      api.get<PageResult<Contact>>(
        `/contacts${buildQuery({ page, page_size: 10, keyword, company_id: companyId })}`,
      ),
  });

  const { data: companies } = useQuery({
    queryKey: ['company-options'],
    queryFn: () => api.get<PageResult<Company>>('/customers?page=1&page_size=200'),
  });

  const createMutation = useMutation({
    mutationFn: (values: Record<string, unknown>) => api.post('/contacts', values),
    onSuccess: () => {
      message.success('联系人创建成功');
      setOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['contacts'] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  const columns: ColumnsType<Contact> = [
    { title: '姓名', dataIndex: 'name', width: 140 },
    {
      title: '客户',
      dataIndex: 'company_name',
      ellipsis: true,
      render: (v: string | null, row) =>
        v ? <a href={`/customers/${row.company_id}`}>{v}</a> : '-',
    },
    { title: '职位', dataIndex: 'position', width: 150, render: (v) => v ?? '-' },
    { title: '邮箱', dataIndex: 'email', width: 220, render: (v) => v ?? '-' },
    { title: '电话', dataIndex: 'phone', width: 140, render: (v) => v ?? '-' },
    { title: '手机', dataIndex: 'mobile', width: 140, render: (v) => v ?? '-' },
    {
      title: '主要',
      dataIndex: 'is_primary',
      width: 90,
      render: (v: boolean) => (v ? <Tag color="gold">主要</Tag> : '-'),
    },
  ];

  return (
    <>
      <PageHeader
        title="联系人管理"
        description="联系人 CRUD，按客户过滤与关键词搜索（对应 F-07）"
        extra={
          <Space>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="姓名/邮箱/电话"
              style={{ width: 200 }}
              onPressEnter={(e) => {
                setPage(1);
                setKeyword((e.target as HTMLInputElement).value);
              }}
            />
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="按客户筛选"
              style={{ width: 220 }}
              value={companyId}
              onChange={(v) => {
                setPage(1);
                setCompanyId(v);
              }}
              options={(companies?.items ?? []).map((c) => ({ value: c.id, label: c.name }))}
            />
            <Button icon={<ReloadOutlined />} onClick={() => refetch()} />
            <HasPermission permission="contact:create">
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
                新建联系人
              </Button>
            </HasPermission>
          </Space>
        }
      />

      <Table<Contact>
        rowKey="id"
        size="small"
        loading={isFetching}
        columns={columns}
        dataSource={data?.items ?? []}
        scroll={{ x: 1100 }}
        pagination={{
          current: data?.page ?? 1,
          pageSize: data?.page_size ?? 10,
          total: data?.total ?? 0,
          onChange: setPage,
        }}
      />

      <Modal
        title="新建联系人"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending}
        destroyOnClose
      >
        <Form form={form} layout="vertical" requiredMark={false} onFinish={(v) => createMutation.mutate(v)}>
          <Form.Item name="company_id" label="所属客户">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="选择客户"
              options={(companies?.items ?? []).map((c) => ({ value: c.id, label: c.name }))}
            />
          </Form.Item>
          <Form.Item name="name" label="姓名" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="position" label="职位">
            <Input />
          </Form.Item>
          <Form.Item name="email" label="邮箱">
            <Input />
          </Form.Item>
          <Form.Item name="phone" label="电话">
            <Input />
          </Form.Item>
          <Form.Item name="mobile" label="手机">
            <Input />
          </Form.Item>
          <Form.Item name="is_primary" label="主要联系人" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
