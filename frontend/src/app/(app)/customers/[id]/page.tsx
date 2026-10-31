'use client';

import { ArrowLeftOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App,
  Button,
  Card,
  Descriptions,
  Empty,
  Form,
  Modal,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { api } from '@/lib/api';
import { formatDate, formatDateTime, formatMoney } from '@/lib/format';
import type { BusinessCodeItem, CompanyDetail, CurrencyCodeResult } from '@/types/business';

export default function CustomerDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id as string;
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<{ currency: string }>();

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['customer', id],
    queryFn: () => api.get<CompanyDetail>(`/customers/${id}`),
    enabled: !!id,
  });

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

  if (!data) {
    return <Empty description={isFetching ? '加载中...' : '客户不存在'} />;
  }

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
                <Descriptions.Item label="国家">{data.country ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="行业">{data.industry ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="客户等级">
                  {data.customer_level ? <Tag color="blue">{data.customer_level}</Tag> : '-'}
                </Descriptions.Item>
                <Descriptions.Item label="来源">{data.source ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="官网">{data.website ?? '-'}</Descriptions.Item>
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
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                dataSource={data.contacts}
                columns={[
                  { title: '姓名', dataIndex: 'name', width: 140 },
                  { title: '职位', dataIndex: 'position', render: (v) => v ?? '-' },
                  { title: '邮箱', dataIndex: 'email', render: (v) => v ?? '-' },
                  { title: '电话', dataIndex: 'phone', render: (v) => v ?? '-' },
                  { title: '手机', dataIndex: 'mobile', render: (v) => v ?? '-' },
                  {
                    title: '主要联系人',
                    dataIndex: 'is_primary',
                    width: 110,
                    render: (v: boolean) => (v ? <Tag color="gold">主要</Tag> : '-'),
                  },
                ]}
              />
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
    </>
  );
}
