'use client';

import { InboxOutlined, MailOutlined, ReloadOutlined, SendOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Row,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
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
import type { Company, EmailAccount, EmailMessage } from '@/types/business';

function InboxTab() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [direction, setDirection] = useState<string | undefined>();
  const [matched, setMatched] = useState<string | undefined>();
  const [detail, setDetail] = useState<EmailMessage | null>(null);
  const [sendOpen, setSendOpen] = useState(false);
  const [injectOpen, setInjectOpen] = useState(false);
  const [sendForm] = Form.useForm();
  const [injectForm] = Form.useForm();

  const query = useQuery({
    queryKey: ['emails', page, keyword, direction, matched],
    queryFn: () =>
      api.get<PageResult<EmailMessage>>(
        `/emails${buildQuery({
          page,
          page_size: 10,
          keyword,
          direction,
          matched: matched === undefined ? undefined : matched === 'true',
        })}`,
      ),
  });

  const detailQuery = useQuery({
    queryKey: ['email', detail?.id],
    queryFn: () => api.get<EmailMessage>(`/emails/${detail?.id}`),
    enabled: !!detail,
  });

  const companies = useQuery({
    queryKey: ['company-options'],
    queryFn: () => api.get<PageResult<Company>>('/customers?page=1&page_size=200'),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['emails'] });

  const sync = useMutation({
    mutationFn: () => api.post('/emails/sync', { limit: 20 }),
    onSuccess: (res) => {
      const r = res as { fetched: number; created: number; matched: number; detail: string };
      message.info(`${r.detail}（拉取 ${r.fetched}，新增 ${r.created}，自动关联 ${r.matched}）`);
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const send = useMutation({
    mutationFn: (values: Record<string, unknown>) => api.post('/emails/send', values),
    onSuccess: (res) => {
      const r = res as { send_status: string; simulated: boolean };
      message.success(`邮件已处理：${r.send_status}${r.simulated ? '（模拟模式）' : ''}`);
      setSendOpen(false);
      sendForm.resetFields();
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const inject = useMutation({
    mutationFn: (values: { from_addr: string; subject?: string; body?: string }) =>
      api.post(
        `/emails/inject-inbound${buildQuery({
          from_addr: values.from_addr,
          subject: values.subject,
          body: values.body,
        })}`,
      ),
    onSuccess: (res) => {
      const r = res as { auto_matched: boolean; match_type: string | null };
      message.success(
        r.auto_matched ? `已注入并自动关联（${r.match_type}）` : '已注入，未匹配到客户（需人工关联）',
      );
      setInjectOpen(false);
      injectForm.resetFields();
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const link = useMutation({
    mutationFn: ({ id, companyId }: { id: string; companyId: string }) =>
      api.post(`/emails/${id}/link`, { company_id: companyId }),
    onSuccess: () => {
      message.success('关联已更新');
      queryClient.invalidateQueries({ queryKey: ['email'] });
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const columns: ColumnsType<EmailMessage> = [
    {
      title: '方向',
      dataIndex: 'direction',
      width: 80,
      render: (v: string) => <StatusTag value={v} />,
    },
    {
      title: '主题',
      dataIndex: 'subject',
      ellipsis: true,
      render: (v: string | null, row) => (
        <a onClick={() => setDetail(row)}>{v || '(无主题)'}</a>
      ),
    },
    {
      title: '发件人',
      dataIndex: 'from_addr',
      width: 220,
      ellipsis: true,
      render: (v: string | null, row) => row.from_name ? `${row.from_name} <${v}>` : (v ?? '-'),
    },
    {
      title: '关联客户',
      dataIndex: 'company_name',
      width: 180,
      render: (v: string | null) => v ?? <Tag color="orange">未关联</Tag>,
    },
    {
      title: '匹配方式',
      dataIndex: 'matched_by',
      width: 130,
      render: (v: string | null) => (v ? <Tag>{v}</Tag> : '-'),
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 170,
      render: (v: string) => formatDateTime(v),
    },
  ];

  return (
    <>
      <Space wrap style={{ marginBottom: 12 }}>
        <Input.Search
          allowClear
          placeholder="主题/发件人/正文"
          style={{ width: 230 }}
          onSearch={(v) => {
            setPage(1);
            setKeyword(v);
          }}
        />
        <Select
          allowClear
          placeholder="方向"
          style={{ width: 120 }}
          value={direction}
          onChange={(v) => {
            setPage(1);
            setDirection(v);
          }}
          options={[
            { value: 'RECEIVED', label: '收件' },
            { value: 'SENT', label: '发件' },
          ]}
        />
        <Select
          allowClear
          placeholder="关联状态"
          style={{ width: 130 }}
          value={matched}
          onChange={(v) => {
            setPage(1);
            setMatched(v);
          }}
          options={[
            { value: 'true', label: '已关联' },
            { value: 'false', label: '未关联' },
          ]}
        />
        <Button icon={<ReloadOutlined />} onClick={() => query.refetch()} />
        <HasPermission permission="email:sync">
          <Button
            icon={<InboxOutlined />}
            loading={sync.isPending}
            onClick={() => sync.mutate()}
          >
            同步 IMAP
          </Button>
          <Button onClick={() => setInjectOpen(true)}>注入演示收件</Button>
        </HasPermission>
        <HasPermission permission="email:send">
          <Button type="primary" icon={<SendOutlined />} onClick={() => setSendOpen(true)}>
            发送邮件
          </Button>
        </HasPermission>
      </Space>

      <Table<EmailMessage>
        rowKey="id"
        size="small"
        loading={query.isFetching}
        columns={columns}
        dataSource={query.data?.items ?? []}
        scroll={{ x: 1100 }}
        pagination={{
          current: query.data?.page ?? 1,
          pageSize: query.data?.page_size ?? 10,
          total: query.data?.total ?? 0,
          onChange: setPage,
        }}
      />

      <Drawer
        title={detail?.subject ?? '邮件详情'}
        open={!!detail}
        onClose={() => setDetail(null)}
        width={640}
      >
        {detailQuery.data ? (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Descriptions bordered size="small" column={1}>
              <Descriptions.Item label="发件人">
                {detailQuery.data.from_name} &lt;{detailQuery.data.from_addr}&gt;
              </Descriptions.Item>
              <Descriptions.Item label="收件人">{detailQuery.data.to_addrs ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="时间">
                {formatDateTime(detailQuery.data.sent_at ?? detailQuery.data.received_at)}
              </Descriptions.Item>
              <Descriptions.Item label="方向">
                <StatusTag value={detailQuery.data.direction} />
                {detailQuery.data.send_status ? (
                  <StatusTag value={detailQuery.data.send_status} />
                ) : null}
              </Descriptions.Item>
              <Descriptions.Item label="关联客户">
                {detailQuery.data.company_name ?? <Tag color="orange">未关联</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label="附件">
                {(detailQuery.data.attachments ?? []).length === 0
                  ? '-'
                  : (detailQuery.data.attachments ?? []).map((a) => (
                      <Tag key={a.id}>{a.filename}</Tag>
                    ))}
              </Descriptions.Item>
            </Descriptions>

            <Card size="small" title="正文">
              <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
                {detailQuery.data.body_text || '(无正文)'}
              </Typography.Paragraph>
            </Card>

            <HasPermission permission="email:view">
              <Card size="small" title="人工确认关联">
                <Select
                  showSearch
                  optionFilterProp="label"
                  style={{ width: '100%' }}
                  placeholder="选择客户以关联该邮件线程"
                  options={(companies.data?.items ?? []).map((c) => ({
                    value: c.id,
                    label: `${c.name}（${c.code}）`,
                  }))}
                  onChange={(companyId) =>
                    detail && link.mutate({ id: detail.id, companyId })
                  }
                />
              </Card>
            </HasPermission>
          </Space>
        ) : (
          <Empty description="加载中..." />
        )}
      </Drawer>

      <Modal
        title="发送邮件"
        open={sendOpen}
        onCancel={() => setSendOpen(false)}
        onOk={() => sendForm.submit()}
        confirmLoading={send.isPending}
        destroyOnClose
      >
        <Form form={sendForm} layout="vertical" onFinish={(v) => send.mutate(v)}>
          <Form.Item name="company_id" label="关联客户">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              options={(companies.data?.items ?? []).map((c) => ({ value: c.id, label: c.name }))}
            />
          </Form.Item>
          <Form.Item
            name="to_addrs"
            label="收件人"
            rules={[{ required: true, message: '请输入收件人' }]}
          >
            <Select mode="tags" placeholder="输入邮箱后回车" tokenSeparators={[',', ';', ' ']} />
          </Form.Item>
          <Form.Item name="subject" label="主题" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="body" label="正文">
            <Input.TextArea rows={5} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="注入演示收件（验证自动关联）"
        open={injectOpen}
        onCancel={() => setInjectOpen(false)}
        onOk={() => injectForm.submit()}
        confirmLoading={inject.isPending}
        destroyOnClose
      >
        <Typography.Paragraph type="secondary">
          使用已存在的联系人邮箱（如种子数据中的 david@blueocean-trading.co.uk）可验证「按联系人邮箱自动关联」。
        </Typography.Paragraph>
        <Form
          form={injectForm}
          layout="vertical"
          onFinish={(v) => inject.mutate(v)}
          initialValues={{ subject: 'Re: Quotation inquiry', body: 'Thanks, we are reviewing.' }}
        >
          <Form.Item
            name="from_addr"
            label="发件人邮箱"
            rules={[{ required: true, message: '请输入发件人邮箱' }]}
          >
            <Input placeholder="david@blueocean-trading.co.uk" />
          </Form.Item>
          <Form.Item name="subject" label="主题">
            <Input />
          </Form.Item>
          <Form.Item name="body" label="正文">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}

function AccountsTab() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const query = useQuery({
    queryKey: ['email-accounts'],
    queryFn: () => api.get<EmailAccount[]>('/email-accounts'),
  });

  const create = useMutation({
    mutationFn: (values: Record<string, unknown>) => api.post('/email-accounts', values),
    onSuccess: () => {
      message.success('账号已创建');
      setOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['email-accounts'] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  const columns: ColumnsType<EmailAccount> = [
    { title: '名称', dataIndex: 'name', width: 180 },
    { title: '邮箱', dataIndex: 'email', width: 220 },
    {
      title: 'SMTP / IMAP',
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <span style={{ fontSize: 12 }}>SMTP: {row.smtp_host ?? '-'}</span>
          <span style={{ fontSize: 12 }}>IMAP: {row.imap_host ?? '-'}</span>
        </Space>
      ),
    },
    {
      title: '模式',
      dataIndex: 'simulated',
      width: 110,
      render: (v: boolean) =>
        v ? <Tag color="orange">模拟模式</Tag> : <Tag color="green">真实收发</Tag>,
    },
    {
      title: '默认',
      dataIndex: 'is_default',
      width: 90,
      render: (v: boolean) => (v ? <Tag color="blue">默认</Tag> : '-'),
    },
    {
      title: '最近同步',
      dataIndex: 'last_sync_at',
      width: 180,
      render: (v: string | null) => formatDateTime(v),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 12 }}>
        <Button icon={<ReloadOutlined />} onClick={() => query.refetch()} />
        <HasPermission permission="email:send">
          <Button type="primary" onClick={() => setOpen(true)}>
            新增账号
          </Button>
        </HasPermission>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          SMTP/IMAP 主机填 <code>demo</code> 即为模拟模式，不实际收发，便于演示完整流程。
        </Typography.Text>
      </Space>

      <Table<EmailAccount>
        rowKey="id"
        size="small"
        loading={query.isFetching}
        columns={columns}
        dataSource={query.data ?? []}
        pagination={false}
      />

      <Modal
        title="新增邮件账号"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={create.isPending}
        width={720}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(v) => create.mutate(v)}
          initialValues={{
            smtp_host: 'demo',
            imap_host: 'demo',
            smtp_port: 465,
            imap_port: 993,
            smtp_ssl: true,
            imap_ssl: true,
            imap_folder: 'INBOX',
            is_default: false,
          }}
        >
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="name" label="账号名称" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="email" label="邮箱地址" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="smtp_host" label="SMTP 主机">
                <Input />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="smtp_port" label="SMTP 端口">
                <Input />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="smtp_user" label="SMTP 账号">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="smtp_password" label="SMTP 密码">
                <Input.Password />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="imap_host" label="IMAP 主机">
                <Input />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="imap_port" label="IMAP 端口">
                <Input />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="imap_user" label="IMAP 账号">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="imap_password" label="IMAP 密码">
                <Input.Password />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="is_default" label="设为默认" valuePropName="checked">
                <Input type="checkbox" style={{ width: 20, height: 20 }} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </>
  );
}

export default function EmailsPage() {
  return (
    <>
      <PageHeader
        title="邮件"
        description="收件箱 / 发送 / IMAP 同步 / 自动关联 + 人工确认（对应 F-17、F-18）"
        extra={<MailOutlined style={{ fontSize: 20, color: '#1677ff' }} />}
      />
      <Tabs
        items={[
          { key: 'inbox', label: '收件箱 / 已发送', children: <InboxTab /> },
          { key: 'accounts', label: '账号配置', children: <AccountsTab /> },
        ]}
      />
    </>
  );
}
