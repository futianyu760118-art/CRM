'use client';

import {
  ArrowLeftOutlined,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  StarOutlined,
} from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App,
  Button,
  Card,
  Descriptions,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { ApiError, api } from '@/lib/api';
import {
  CONTACT_RELATION_OPTIONS,
  CUSTOMER_GROUPS,
  CUSTOMER_SOURCES,
  CUSTOMER_TYPES,
  PAYMENT_METHODS,
  labelOf,
} from '@/lib/dictionaries';
import { formatDate, formatDateTime, formatMoney } from '@/lib/format';
import type {
  BusinessCodeItem,
  CompanyContact,
  CompanyDetail,
  Contact,
  CurrencyCodeResult,
} from '@/types/business';

interface ContactFormValues {
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

export default function CustomerDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id as string;
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [contactOpen, setContactOpen] = useState(false);
  const [form] = Form.useForm<{ currency: string }>();
  const [contactForm] = Form.useForm<ContactFormValues>();

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['customer', id],
    queryFn: () => api.get<CompanyDetail>(`/customers/${id}`),
    enabled: !!id,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['customer', id] });
    queryClient.invalidateQueries({ queryKey: ['customers'] });
    queryClient.invalidateQueries({ queryKey: ['contacts'] });
  };

  const addCurrency = useMutation({
    mutationFn: (currency: string) =>
      api.post<CurrencyCodeResult>(`/customers/${id}/currencies`, { currency }),
    onSuccess: (res) => {
      message.success(
        res.created ? `已追加币别编码 ${res.code}` : `该币别已存在：${res.code}`,
      );
      setOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['customer', id] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  const addContact = useMutation({
    mutationFn: (values: ContactFormValues) =>
      api.post<Contact>('/contacts', { ...values, company_id: id }),
    onSuccess: () => {
      message.success('联系人已添加');
      setContactOpen(false);
      contactForm.resetFields();
      invalidate();
    },
    onError: (e: Error, values: ContactFormValues) => {
      if (e instanceof ApiError && e.status === 409) {
        const existing = (e.data as { existing?: Contact } | undefined)?.existing;
        if (existing) {
          modal.confirm({
            title: '检测到已有相同联系人',
            content: `「${existing.name}」已存在（${
              existing.email ?? existing.mobile ?? existing.phone ?? existing.wechat ?? '同姓名'
            }）。可将其关联到当前客户，或仍然新建独立联系人。`,
            okText: '关联到已有联系人',
            cancelText: '仍然新建独立联系人',
            onOk: () =>
              api.post(`/contacts/${existing.id}/links`, {
                company_id: id,
                relation_type: values.relation_type,
                is_primary: values.is_primary,
              }),
            onCancel: () => {
              api
                .post<Contact>('/contacts', {
                  ...values,
                  company_id: id,
                  force_independent: true,
                })
                .then(() => {
                  message.success('已新建独立联系人');
                  setContactOpen(false);
                  contactForm.resetFields();
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

  const setPrimary = useMutation({
    mutationFn: (contactId: string) =>
      api.put(`/contacts/${contactId}/primary`, { company_id: id }),
    onSuccess: () => {
      message.success('已设为主要联系人');
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const removeLink = useMutation({
    mutationFn: (contactId: string) => api.delete(`/contacts/${contactId}/links/${id}`),
    onSuccess: () => {
      message.success('已解除该联系人与当前客户的关联');
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  if (!data) {
    return <Empty description={isFetching ? '加载中...' : '客户不存在'} />;
  }

  const contactColumns = [
    { title: '姓名', dataIndex: 'name', width: 120 },
    { title: '职位', dataIndex: 'position', width: 110, render: (v: string | null) => v ?? '-' },
    {
      title: '关系类型',
      dataIndex: 'relation_label',
      width: 110,
      render: (v: string | null, row: CompanyContact) =>
        v ? <Tag color="geekblue">{v ?? row.relation_type}</Tag> : '-',
    },
    { title: '邮箱', dataIndex: 'email', render: (v: string | null) => v ?? '-' },
    { title: '电话', dataIndex: 'phone', width: 130, render: (v: string | null) => v ?? '-' },
    { title: '手机', dataIndex: 'mobile', width: 130, render: (v: string | null) => v ?? '-' },
    { title: '微信', dataIndex: 'wechat', width: 120, render: (v: string | null) => v ?? '-' },
    { title: 'WhatsApp', dataIndex: 'whatsapp', width: 130, render: (v: string | null) => v ?? '-' },
    {
      title: '主要',
      dataIndex: 'is_primary',
      width: 80,
      render: (v: boolean) => (v ? <Tag color="gold">主要</Tag> : '-'),
    },
    {
      title: '操作',
      width: 190,
      render: (_: unknown, row: CompanyContact) => (
        <Space size={4}>
          {!row.is_primary && (
            <HasPermission permission="contact:update">
              <Button
                size="small"
                type="link"
                icon={<StarOutlined />}
                onClick={() => setPrimary.mutate(row.id)}
              >
                设为主要
              </Button>
            </HasPermission>
          )}
          <HasPermission permission="contact:update">
            <Button
              size="small"
              type="link"
              danger
              icon={<DeleteOutlined />}
              onClick={() =>
                modal.confirm({
                  title: '解除关联',
                  content: `确认将「${row.name}」从当前客户关联中移除？（不会删除联系人主档）`,
                  okText: '解除',
                  okButtonProps: { danger: true },
                  onOk: () => removeLink.mutate(row.id),
                })
              }
            >
              解除关联
            </Button>
          </HasPermission>
        </Space>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title={`${data.name}（${data.code}）`}
        description={data.name_en ?? undefined}
        extra={
          <Space>
            <Link href="/customers">
              <Button icon={<ArrowLeftOutlined />}>返回列表</Button>
            </Link>
            <Button icon={<ReloadOutlined />} onClick={() => refetch()} />
            <HasPermission permission="customer:update">
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
                追加币别编码
              </Button>
            </HasPermission>
          </Space>
        }
      />

      <Tabs
        items={[
          {
            key: 'info',
            label: '基本信息',
            children: (
              <Descriptions bordered size="small" column={2}>
                <Descriptions.Item label="客户编码">{data.code}</Descriptions.Item>
                <Descriptions.Item label="状态">
                  <StatusTag value={data.status} />
                </Descriptions.Item>
                <Descriptions.Item label="默认币种">
                  <Tag color="cyan">{data.currency}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="负责人">
                  {data.owner_name ?? '-'}
                  {data.owner_seq ? (
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      （该业务员第 {data.owner_seq} 个客户）
                    </Typography.Text>
                  ) : null}
                </Descriptions.Item>
                <Descriptions.Item label="客户分组">
                  {data.customer_group ? (
                    <Tooltip title={data.group_reason}>
                      <Tag
                        color={
                          data.customer_group === 'new'
                            ? 'green'
                            : data.customer_group === 'dormant'
                              ? 'default'
                              : 'blue'
                        }
                      >
                        {labelOf(CUSTOMER_GROUPS, data.customer_group)}
                      </Tag>
                    </Tooltip>
                  ) : (
                    '-'
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="客户等级">
                  {data.customer_level ? <Tag color="blue">{data.customer_level}</Tag> : '-'}
                </Descriptions.Item>
                <Descriptions.Item label="来源">{labelOf(CUSTOMER_SOURCES, data.source)}</Descriptions.Item>
                <Descriptions.Item label="客户类型">
                  {labelOf(CUSTOMER_TYPES, data.customer_type)}
                </Descriptions.Item>
                <Descriptions.Item label="国家">{data.country ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="行业">{data.industry ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="付款方式">
                  {labelOf(PAYMENT_METHODS, data.payment_method)}
                </Descriptions.Item>
                <Descriptions.Item label="品牌">{data.brand ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="主营产品" span={2}>
                  {data.main_products ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="销售渠道及市场" span={2}>
                  {data.sales_channel_market ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="官网" span={2}>
                  {data.website ? (
                    <a href={data.website} target="_blank" rel="noreferrer">
                      {data.website}
                    </a>
                  ) : (
                    '-'
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="编码规则" span={2}>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {data.code_rule ?? '业务员编号-业务员第N个客户-公司第N个客户'}
                    {data.global_seq ? ` ｜ 本客户为公司第 ${data.global_seq} 个客户` : ''}
                  </Typography.Text>
                </Descriptions.Item>
                <Descriptions.Item label="K3 同步">
                  {data.sync_status ? <StatusTag value={data.sync_status} /> : '-'}
                </Descriptions.Item>
                <Descriptions.Item label="地址" span={2}>
                  {data.address ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="公司背景" span={2}>
                  <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
                    {data.company_background ?? '-'}
                  </Typography.Paragraph>
                </Descriptions.Item>
                <Descriptions.Item label="备注" span={2}>
                  {data.remark ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="创建时间" span={2}>
                  {formatDateTime(data.created_at)}
                </Descriptions.Item>
              </Descriptions>
            ),
          },
          {
            key: 'codes',
            label: `业务编码 (${(data.business_codes ?? []).length})`,
            children: (
              <>
                <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
                  主编码为三段式客户编码；同一客户不同币别在此追加 -1 / -2 …
                </Typography.Paragraph>
                <Table<BusinessCodeItem>
                  rowKey="id"
                  size="small"
                  pagination={false}
                  dataSource={data.business_codes ?? []}
                  columns={[
                    { title: '编码', dataIndex: 'code', width: 260 },
                    {
                      title: '类型',
                      dataIndex: 'code_type',
                      width: 120,
                      render: (v: string) =>
                        v === 'INTERNAL' ? (
                          <Tag color="blue">主编码</Tag>
                        ) : (
                          <Tag color="cyan">币别编码</Tag>
                        ),
                    },
                    {
                      title: '币种',
                      dataIndex: 'currency',
                      width: 100,
                      render: (v: string | null) => v ?? '-',
                    },
                    {
                      title: '主码',
                      dataIndex: 'is_primary',
                      width: 80,
                      render: (v: boolean) => (v ? <Tag color="gold">是</Tag> : '-'),
                    },
                  ]}
                />
                <HasPermission permission="customer:update">
                  <Button
                    style={{ marginTop: 12 }}
                    icon={<PlusOutlined />}
                    onClick={() => setOpen(true)}
                  >
                    追加币别编码
                  </Button>
                </HasPermission>
              </>
            ),
          },
          {
            key: 'contacts',
            label: `联系人 (${data.contacts.length})`,
            children: (
              <>
                <Space style={{ marginBottom: 12 }}>
                  <HasPermission permission="contact:create">
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={() => setContactOpen(true)}
                    >
                      添加联系人
                    </Button>
                  </HasPermission>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    同一联系人可关联多个客户；主要联系人用于客户列表展示。
                  </Typography.Text>
                </Space>
                <Table<CompanyContact>
                  rowKey="link_id"
                  size="small"
                  pagination={false}
                  dataSource={data.contacts}
                  scroll={{ x: 1280 }}
                  columns={contactColumns}
                />
              </>
            ),
          },
          {
            key: 'opportunities',
            label: `商机 (${data.opportunities.length})`,
            children: (
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                dataSource={data.opportunities}
                columns={[
                  {
                    title: '商机编号',
                    dataIndex: 'opportunity_no',
                    width: 170,
                    render: (v: string, row) => <Link href={`/opportunities/${row.id}`}>{v}</Link>,
                  },
                  { title: '商机名称', dataIndex: 'name' },
                  {
                    title: '阶段',
                    dataIndex: 'stage',
                    width: 120,
                    render: (v: string) => <StatusTag value={v} />,
                  },
                  {
                    title: '预计金额',
                    dataIndex: 'estimated_amount',
                    width: 160,
                    render: (v: number | null, row) => formatMoney(v, row.currency),
                  },
                ]}
              />
            ),
          },
          {
            key: 'inquiries',
            label: `询价 (${data.inquiries.length})`,
            children: (
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                dataSource={data.inquiries}
                columns={[
                  {
                    title: '询价单号',
                    dataIndex: 'inquiry_no',
                    width: 170,
                    render: (v: string, row) => <Link href={`/inquiries/${row.id}`}>{v}</Link>,
                  },
                  {
                    title: '状态',
                    dataIndex: 'status',
                    width: 120,
                    render: (v: string) => <StatusTag value={v} />,
                  },
                  { title: '币种', dataIndex: 'currency', width: 90 },
                  {
                    title: '创建时间',
                    dataIndex: 'created_at',
                    width: 180,
                    render: (v: string | null) => formatDateTime(v),
                  },
                ]}
              />
            ),
          },
          {
            key: 'emails',
            label: `邮件 (${data.email_threads.length})`,
            children:
              data.email_threads.length === 0 ? (
                <Empty description="暂无邮件往来" />
              ) : (
                <Table
                  rowKey="id"
                  size="small"
                  pagination={false}
                  dataSource={data.email_threads}
                  columns={[
                    { title: '主题', dataIndex: 'subject', render: (v) => v ?? '(无主题)' },
                    { title: '邮件数', dataIndex: 'message_count', width: 100 },
                    {
                      title: '最近往来',
                      dataIndex: 'last_message_at',
                      width: 180,
                      render: (v: string | null) => formatDateTime(v),
                    },
                    {
                      title: '操作',
                      width: 100,
                      render: () => <Link href="/emails">查看</Link>,
                    },
                  ]}
                />
              ),
          },
        ]}
      />

      <Card size="small" style={{ marginTop: 16 }}>
        <Typography.Text type="secondary">
          提示：报价与核价信息请在「报价管理 / 核价管理」中查看；邮件时间轴见「邮件」模块。
        </Typography.Text>
        <Typography.Text type="secondary" style={{ marginLeft: 12 }}>
          最近更新：{formatDate(data.created_at)}
        </Typography.Text>
      </Card>

      <Modal
        title="追加币别编码"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={addCurrency.isPending}
        destroyOnClose
      >
        <Typography.Paragraph type="secondary">
          客户主编码为 <code>{data.code}</code>；新增币别后编码形如{' '}
          <code>{data.code}-1</code>（已存在则直接返回原编码）。
        </Typography.Paragraph>
        <Form form={form} layout="vertical" onFinish={(v) => addCurrency.mutate(v.currency)}>
          <Form.Item name="currency" label="币种" rules={[{ required: true, message: '请选择币种' }]}>
            <Select
              options={['USD', 'EUR', 'CNY', 'GBP', 'JPY', 'AUD'].map((v) => ({
                value: v,
                label: v,
              }))}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="添加联系人"
        open={contactOpen}
        onCancel={() => setContactOpen(false)}
        onOk={() => contactForm.submit()}
        confirmLoading={addContact.isPending}
        destroyOnClose
      >
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          系统会按邮箱/电话/手机/微信检测是否已有同一联系人，可关联到已有联系人，避免重复建档。
        </Typography.Paragraph>
        <Form
          form={contactForm}
          layout="vertical"
          initialValues={{ relation_type: 'OTHER', is_primary: false }}
          onFinish={(v) => addContact.mutate(v)}
        >
          <Form.Item name="name" label="姓名" rules={[{ required: true, message: '请输入姓名' }]}>
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
          <Form.Item name="is_primary" label="设为主要联系人" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
