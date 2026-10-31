'use client';

import {
  ArrowLeftOutlined,
  EditOutlined,
  FileExcelOutlined,
  FilePdfOutlined,
  MailOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Form,
  Image,
  Input,
  Modal,
  Row,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { API_BASE_URL, api, fileUrl } from '@/lib/api';
import { useAuthStore } from '@/lib/auth-store';
import { formatDate, formatDateTime, formatNumber } from '@/lib/format';
import type { Quotation, QuotationItem } from '@/types/business';

function downloadWithAuth(url: string, filename: string, token: string | null) {
  fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    .then((res) => {
      if (!res.ok) throw new Error(`导出失败 (${res.status})`);
      return res.blob();
    })
    .then((blob) => {
      const href = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = href;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(href);
    })
    .catch((e: Error) => window.alert(e.message));
}

export default function QuotationDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id as string;
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const accessToken = useAuthStore((s) => s.accessToken);
  const [sendOpen, setSendOpen] = useState(false);
  const [form] = Form.useForm();

  const query = useQuery({
    queryKey: ['quotation', id],
    queryFn: () => api.get<Quotation>(`/quotations/${id}`),
    enabled: !!id,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['quotation', id] });
    queryClient.invalidateQueries({ queryKey: ['quotations'] });
    queryClient.invalidateQueries({ queryKey: ['approvals'] });
  };

  const submit = useMutation({
    mutationFn: () => api.post(`/quotations/${id}/submit`),
    onSuccess: () => {
      message.success('已提交审批');
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const approve = useMutation({
    mutationFn: (approved: boolean) =>
      api.post(`/quotations/${id}/approve?approved=${approved}`, { approved }),
    onSuccess: () => {
      message.success('审批完成');
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const generatePdf = useMutation({
    mutationFn: () => api.post(`/quotations/${id}/generate-pdf`),
    onSuccess: (res) => {
      const result = res as { detail: string; size: number };
      message.success(`${result.detail}，${result.size} bytes`);
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const sendEmail = useMutation({
    mutationFn: (values: { to_addrs?: string }) =>
      api.post(
        `/quotations/${id}/send-email${values.to_addrs ? `?to_addrs=${encodeURIComponent(values.to_addrs)}` : ''}`,
        undefined,
      ),
    onSuccess: (res) => {
      const result = res as { send_status: string; to: string[]; simulated: boolean };
      message.success(
        `邮件${result.simulated ? '（模拟）' : ''}已发送 -> ${result.to.join(', ')} [${result.send_status}]`,
      );
      setSendOpen(false);
      form.resetFields();
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  if (!query.data) {
    return <Empty description={query.isFetching ? '加载中...' : '报价单不存在'} />;
  }

  const data = query.data;
  const items = data.items ?? [];

  const columns: ColumnsType<QuotationItem> = [
    { title: '#', width: 46, align: 'center', render: (_v, _r, i) => i + 1 },
    {
      title: 'Picture',
      dataIndex: 'image_file_id',
      width: 80,
      render: (v: string | null) =>
        v ? (
        <Image
          src={fileUrl(v)}
          alt="产品图"
          width={54}
          height={54}
          style={{ objectFit: 'cover' }}
        />
      ) : (
        '-'
      ),
    },
    { title: 'Item No.', dataIndex: 'item_no', width: 150, render: (v, row) => v ?? row.product_name },
    {
      title: 'Description of Goods',
      dataIndex: 'description',
      render: (v: string | null) => (
        <Typography.Text style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{v ?? '-'}</Typography.Text>
      ),
    },
    {
      title: `Price (${data.currency})`,
      dataIndex: 'unit_price',
      width: 110,
      align: 'right',
      render: (v: number) => formatNumber(v, 2),
    },
    { title: 'MOQ', dataIndex: 'moq', width: 90, render: (v) => v ?? '-' },
    { title: 'Power (W)', dataIndex: 'power', width: 90, render: (v) => v ?? '-' },
    { title: 'IP', dataIndex: 'ip', width: 70, render: (v) => v ?? '-' },
    { title: 'Lumen (lm)', dataIndex: 'lumen', width: 100, render: (v) => v ?? '-' },
    { title: 'Color TEMP.', dataIndex: 'color_temp', width: 110, render: (v) => v ?? '-' },
    {
      title: 'Color Rendering (Ra)',
      dataIndex: 'color_rendering',
      width: 140,
      render: (v) => v ?? '-',
    },
    { title: 'Price Valid', dataIndex: 'price_valid', width: 120, render: (v) => v ?? '-' },
  ];

  return (
    <>
      <PageHeader
        title={`${data.title ?? 'Offer'} · ${data.quotation_no}`}
        description={`${data.company_name ?? ''}${data.buyer_attn ? ` · Attn: ${data.buyer_attn}` : ''}`}
        extra={
          <Space wrap>
            <Link href="/quotations">
              <Button icon={<ArrowLeftOutlined />}>返回列表</Button>
            </Link>
            <Button icon={<ReloadOutlined />} onClick={() => query.refetch()} />
            <HasPermission permission="quotation:submit">
              <Button
                type="primary"
                disabled={!['DRAFT', 'REJECTED'].includes(data.status)}
                loading={submit.isPending}
                onClick={() => submit.mutate()}
              >
                提交审批
              </Button>
            </HasPermission>
            <HasPermission permission="quotation:approve">
              <Button disabled={data.status !== 'PENDING_APPROVAL'} onClick={() => approve.mutate(true)}>
                审批通过
              </Button>
            </HasPermission>
            <HasPermission permission="quotation:update">
              <Link href={`/quotations/${data.id}/edit`}>
                <Button icon={<EditOutlined />} disabled={!['DRAFT', 'REJECTED'].includes(data.status)}>
                  编辑
                </Button>
              </Link>
            </HasPermission>
            <HasPermission permission="quotation:pdf">
              <Button icon={<FilePdfOutlined />} loading={generatePdf.isPending} onClick={() => generatePdf.mutate()}>
                生成 PDF
              </Button>
            </HasPermission>
            <Button
              icon={<FileExcelOutlined />}
              onClick={() =>
                downloadWithAuth(
                  `${API_BASE_URL}/quotations/${data.id}/export-excel`,
                  `${data.quotation_no}.xlsx`,
                  accessToken,
                )
              }
            >
              导出 Excel
            </Button>
            {data.pdf_file_id ? (
              <Button
                onClick={() =>
                  downloadWithAuth(
                    `${API_BASE_URL}/quotations/${data.id}/pdf`,
                    `${data.quotation_no}.pdf`,
                    accessToken,
                  )
                }
              >
                下载 PDF
              </Button>
            ) : null}
            <HasPermission permission="quotation:send">
              <Button
                icon={<MailOutlined />}
                disabled={!['APPROVED', 'SENT', 'ACCEPTED'].includes(data.status)}
                onClick={() => setSendOpen(true)}
              >
                发送邮件
              </Button>
            </HasPermission>
          </Space>
        }
      />

      <Card size="small" style={{ marginBottom: 16 }}>
        <Descriptions size="small" column={4}>
          <Descriptions.Item label="状态">
            <StatusTag value={data.status} />
          </Descriptions.Item>
          <Descriptions.Item label="币种">{data.currency}</Descriptions.Item>
          <Descriptions.Item label="有效期">
            {data.valid_days} 天（至 {formatDate(data.valid_until)}）
          </Descriptions.Item>
          <Descriptions.Item label="PDF">
            {data.pdf_file_id ? <Tag color="green">已生成</Tag> : <Tag>未生成</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label="贸易术语">{data.incoterm ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="付款条件">{data.payment_terms ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="质保">{data.warranty ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="发送时间">{formatDateTime(data.sent_at)}</Descriptions.Item>
          <Descriptions.Item label="卖方抬头" span={2}>
            {data.seller_name ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label="Add" span={2}>
            {data.seller_address ?? '-'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card size="small" title="产品明细（对外价格表）">
        <Table<QuotationItem>
          rowKey={(r) => r.id ?? String(r.item_no)}
          size="small"
          bordered
          columns={columns}
          dataSource={items}
          pagination={false}
          scroll={{ x: 1500 }}
        />
      </Card>

      {(data.terms ?? []).length > 0 || data.notes_cn || data.notes_en ? (
        <Row gutter={16} style={{ marginTop: 16 }}>
          <Col xs={24} lg={12}>
            <Card size="small" title="▲ 条款">
              {(data.terms ?? []).map((t, i) => (
                <Typography.Paragraph key={i} style={{ fontSize: 12, marginBottom: 4 }}>
                  {t}
                </Typography.Paragraph>
              ))}
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            <Card size="small" title="说明">
              <Typography.Paragraph style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>
                {data.notes_cn ?? '-'}
              </Typography.Paragraph>
              <Typography.Paragraph style={{ fontSize: 12, whiteSpace: 'pre-wrap', color: '#666' }}>
                {data.notes_en ?? ''}
              </Typography.Paragraph>
            </Card>
          </Col>
        </Row>
      ) : null}

      <Modal
        title="发送报价邮件"
        open={sendOpen}
        onCancel={() => setSendOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={sendEmail.isPending}
        destroyOnClose
      >
        <Typography.Paragraph type="secondary">
          留空收件人则自动使用客户主联系人邮箱；未配置真实 SMTP 时以「模拟模式」记录邮件。
          邮件会自动附带报价单 PDF。
        </Typography.Paragraph>
        <Form form={form} layout="vertical" onFinish={(v) => sendEmail.mutate(v)}>
          <Form.Item name="to_addrs" label="收件人（逗号分隔，可留空）">
            <Input placeholder="customer@example.com" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
