'use client';

import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Form, Input, Modal, Select, Space, Switch, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import Link from 'next/link';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import { ApiError, api, buildQuery } from '@/lib/api';
import { CONTACT_RELATION_OPTIONS } from '@/lib/dictionaries';
import type { PageResult } from '@/types';
import type { Company, Contact } from '@/types/business';

interface ContactFormValues {
  company_id?: string;
  name: string;
  position?: string;
  email?: string;
  phone?: string;
  mobile?: string;
  wechat?: string;
  whatsapp?: string;
  relation_type: string;
  is_primary: boolean;
}

export default function ContactsPage() {
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [companyId, setCompanyId] = useState<string | undefined>();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<ContactFormValues>();

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

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['contacts'] });
    queryClient.invalidateQueries({ queryKey: ['customers'] });
  };

  const createMutation = useMutation({
    mutationFn: (values: ContactFormValues) => api.post<Contact>('/contacts', values),
    onSuccess: () => {
      message.success('联系人创建成功');
      setOpen(false);
      form.resetFields();
      invalidate();
    },
    onError: (e: Error, values: ContactFormValues) => {
      if (e instanceof ApiError && e.status === 409) {
        const existing = (e.data as { existing?: Contact } | undefined)?.existing;
        if (existing && values.company_id) {
          modal.confirm({
            title: '检测到已有相同联系人',
            content: `「${existing.name}」已存在（${
              existing.email ?? existing.mobile ?? existing.phone ?? existing.wechat ?? '同姓名'
            }）。可将其关联到所选客户，或仍然新建独立联系人。`,
            okText: '关联到已有联系人',
            cancelText: '仍然新建独立联系人',
            onOk: () =>
              api
                .post(`/contacts/${existing.id}/links`, {
                  company_id: values.company_id,
                  relation_type: values.relation_type,
                  is_primary: values.is_primary,
                })
                .then(() => {
                  message.success('已关联到已有联系人');
                  setOpen(false);
                  form.resetFields();
                  invalidate();
                })
                .catch((err: Error) => message.error(err.message)),
            onCancel: () => {
              api
                .post<Contact>('/contacts', { ...values, force_independent: true })
                .then(() => {
                  message.success('已新建独立联系人');
                  setOpen(false);
                  form.resetFields();
                  invalidate();
                })
                .catch((err: Error) => message.error(err.message));
            },
          });
          return;
        }
      }
      message.error(e.message);
    },
  });

  const columns: ColumnsType<Contact> = [
    { title: '姓名', dataIndex: 'name', width: 130 },
    {
      title: '客户',
      dataIndex: 'company_name',
      ellipsis: true,
      render: (v: string | null, row) => {
        const extra = (row.companies?.length ?? 0) > 1 ? ` +${row.companies.length - 1}` : '';
        return v ? (
          <span>
            <Link href={`/customers/${row.companies?.[0]?.company_id ?? row.company_id}`}>{v}</Link>
            {extra}
          </span>
        ) : (
          '-'
        );
      },
    },
    {
      title: '关系类型',
      dataIndex: 'relation_label',
      width: 110,
      render: (v: string | null, row) =>
        v ? <Tag color="geekblue">{v ?? row.relation_type}</Tag> : '-',
    },
    { title: '职位', dataIndex: 'position', width: 130, render: (v) => v ?? '-' },
    { title: '邮箱', dataIndex: 'email', width: 210, render: (v) => v ?? '-' },
    { title: '电话', dataIndex: 'phone', width: 130, render: (v) => v ?? '-' },
    { title: '手机', dataIndex: 'mobile', width: 130, render: (v) => v ?? '-' },
    { title: '微信', dataIndex: 'wechat', width: 120, render: (v) => v ?? '-' },
    { title: 'WhatsApp', dataIndex: 'whatsapp', width: 130, render: (v) => v ?? '-' },
    {
      title: '主要',
      dataIndex: 'is_primary',
      width: 80,
      render: (v: boolean) => (v ? <Tag color="gold">主要</Tag> : '-'),
    },
  ];

  return (
    <>
      <PageHeader
        title="联系人管理"
        description="联系人主档、一人多客户关联与主要联系人（对应 F-07、CONT-04）"
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
        scroll={{ x: 1400 }}
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
        <Form
          form={form}
          layout="vertical"
          requiredMark={false}
          initialValues={{ relation_type: 'OTHER', is_primary: false }}
          onFinish={(v) => createMutation.mutate(v)}
        >
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
          <Form.Item name="email" label="邮箱" rules={[{ type: 'email', message: '邮箱格式不正确' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="phone" label="电话">
            <Input />
          </Form.Item>
          <Form.Item name="mobile" label="手机">
            <Input />
          </Form.Item>
          <Form.Item name="wechat" label="微信">
            <Input />
          </Form.Item>
          <Form.Item
            name="whatsapp"
            label="WhatsApp"
            tooltip="仅允许数字、空格、+ 与 -"
            rules={[{ pattern: /^[+0-9\s-]*$/, message: 'WhatsApp 仅允许数字、空格、+ 与 -' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="relation_type" label="关系类型">
            <Select options={CONTACT_RELATION_OPTIONS} />
          </Form.Item>
          <Form.Item name="is_primary" label="主要联系人" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
