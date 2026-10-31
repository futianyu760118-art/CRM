'use client';

import {
  ArrowLeftOutlined,
  CalculatorOutlined,
  EditOutlined,
  FileExcelOutlined,
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
  InputNumber,
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
import { formatDate, formatDateTime, formatMoney, formatNumber } from '@/lib/format';
import type { Inquiry, InquiryItem, Pricing } from '@/types/business';

const COST_FIELDS: { name: string; label: string }[] = [
  { name: 'material_cost', label: '材料成本' },
  { name: 'labor_cost', label: '人工成本' },
  { name: 'packaging_cost', label: '包装成本' },
  { name: 'freight_cost', label: '运费' },
  { name: 'tooling_cost', label: '模具费' },
  { name: 'customization_cost', label: '定制费' },
  { name: 'moq_cost', label: '起订量成本' },
  { name: 'other_cost', label: '其他成本' },
  { name: 'loss_cost', label: '损耗成本' },
];

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

const ITEM_COLUMNS: ColumnsType<InquiryItem> = [
  { title: '序号', width: 54, align: 'center', render: (_v, _r, i) => i + 1 },
  {
    title: '产品图',
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
  { title: '产品型号', dataIndex: 'product_model', width: 150, render: (v) => v ?? '-' },
  { title: '产品名称', dataIndex: 'product_name', width: 140, render: (v) => v ?? '-' },
  { title: '功率', dataIndex: 'power', width: 80, render: (v) => v ?? '-' },
  { title: '输入电压', dataIndex: 'voltage', width: 90, render: (v) => v ?? '-' },
  { title: '电池', dataIndex: 'battery', width: 110, render: (v) => v ?? '-' },
  { title: '色温', dataIndex: 'color_temp', width: 80, render: (v) => v ?? '-' },
  { title: '光通量/光效', dataIndex: 'lumen', width: 100, render: (v) => v ?? '-' },
  { title: '光源', dataIndex: 'light_source', width: 70, render: (v) => v ?? '-' },
  { title: '主体', dataIndex: 'main_body', width: 80, render: (v) => v ?? '-' },
  { title: '压框', dataIndex: 'frame', width: 70, render: (v) => v ?? '-' },
  { title: '灯罩', dataIndex: 'lamp_shade', width: 80, render: (v) => v ?? '-' },
  { title: '反光罩', dataIndex: 'reflector', width: 80, render: (v) => v ?? '-' },
  { title: '电缆线', dataIndex: 'cable', width: 160, render: (v) => v ?? '-' },
  { title: '开关', dataIndex: 'switch', width: 90, render: (v) => v ?? '-' },
  { title: 'USB', dataIndex: 'usb', width: 70, render: (v) => v ?? '-' },
  { title: '防水等级', dataIndex: 'waterproof', width: 85, render: (v) => v ?? '-' },
  { title: '感应器', dataIndex: 'sensor', width: 140, render: (v) => v ?? '-' },
  { title: '其他要求', dataIndex: 'other_requirement', width: 150, render: (v) => v ?? '-' },
  { title: '其他要求2', dataIndex: 'other_requirement2', width: 140, render: (v) => v ?? '-' },
  {
    title: '报价',
    dataIndex: 'quote_price',
    width: 90,
    render: (v: number | null) => (v === null ? '-' : formatNumber(v, 2)),
  },
  {
    title: '目标价',
    dataIndex: 'target_price',
    width: 90,
    render: (v: number | null) => (v === null ? '-' : formatNumber(v, 2)),
  },
  {
    title: '需求数量',
    dataIndex: 'quantity',
    width: 90,
    render: (v: number) => (v ? formatNumber(v) : '-'),
  },
  { title: '报价需时间', dataIndex: 'quote_lead_time', width: 110, render: (v) => v ?? '-' },
];

export default function InquiryDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id as string;
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const accessToken = useAuthStore((s) => s.accessToken);
  const [pricingOpen, setPricingOpen] = useState(false);
  const [form] = Form.useForm();

  const inquiry = useQuery({
    queryKey: ['inquiry', id],
    queryFn: () => api.get<Inquiry>(`/inquiries/${id}`),
    enabled: !!id,
  });

  const versions = useQuery({
    queryKey: ['pricing-versions', id],
    queryFn: () => api.get<Pricing[]>(`/inquiries/${id}/pricing-versions`),
    enabled: !!id,
  });

  const createPricing = useMutation({
    mutationFn: (values: Record<string, unknown>) => {
      const costs: Record<string, number> = {};
      COST_FIELDS.forEach((f) => {
        costs[f.name] = Number(values[f.name] ?? 0);
      });
      return api.post('/pricing', {
        inquiry_id: id,
        currency: inquiry.data?.currency ?? 'RMB',
        target_margin: values.target_margin,
        discount_rate: values.discount_rate,
        costs,
      });
    },
    onSuccess: () => {
      message.success('核价记录已创建（新版本）');
      setPricingOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['pricing-versions', id] });
      queryClient.invalidateQueries({ queryKey: ['inquiry', id] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  const submitPricing = useMutation({
    mutationFn: (pricingId: string) => api.post(`/pricing/${pricingId}/submit`),
    onSuccess: () => {
      message.success('核价已提交审批');
      queryClient.invalidateQueries({ queryKey: ['pricing-versions', id] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  if (!inquiry.data) {
    return <Empty description={inquiry.isFetching ? '加载中...' : '询价单不存在'} />;
  }

  const data = inquiry.data;
  const items = data.items ?? [];
  const newItems = items.filter((i) => (i.group_type ?? 'EXISTING') === 'NEW');
  const existingItems = items.filter((i) => (i.group_type ?? 'EXISTING') !== 'NEW');
  const specRows = (data.spec_rows ?? []).filter(
    (r) => (r.values ?? []).some((v) => v) || r.label === '产品图片',
  );
  const specWidth = specRows.reduce((max, r) => Math.max(max, (r.values ?? []).length), 0);
  const latestApproved = (versions.data ?? []).find((v) => v.status === 'APPROVED');

  const generateQuotation = async () => {
    if (!latestApproved) return;
    try {
      const res = (await api.post('/quotations/from-pricing', {
        pricing_id: latestApproved.id,
        incoterm: data.trade_terms ?? 'FOB',
        payment_terms: data.payment_terms ?? '30% T/T',
      })) as { id: string; quotation_no: string };
      message.success(`报价单 ${res.quotation_no} 已生成`);
      queryClient.invalidateQueries({ queryKey: ['quotations'] });
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  return (
    <>
      <PageHeader
        title={`询价单 ${data.inquiry_no}`}
        description={`${data.customer_name ?? ''} ${data.owner_name_text ? `· ${data.owner_name_text}` : ''} ${data.market ? `· ${data.market}` : ''}`}
        extra={
          <Space wrap>
            <Link href="/inquiries">
              <Button icon={<ArrowLeftOutlined />}>返回列表</Button>
            </Link>
            <Button icon={<ReloadOutlined />} onClick={() => inquiry.refetch()} />
            <Button
              icon={<FileExcelOutlined />}
              onClick={() =>
                downloadWithAuth(
                  `${API_BASE_URL}/inquiries/${data.id}/export-excel`,
                  `${data.inquiry_no}.xlsx`,
                  accessToken,
                )
              }
            >
              导出 Excel
            </Button>
            <HasPermission permission="inquiry:update">
              <Link href={`/inquiries/${data.id}/edit`}>
                <Button icon={<EditOutlined />}>编辑</Button>
              </Link>
            </HasPermission>
            <HasPermission permission="pricing:create">
              <Button
                type="primary"
                icon={<CalculatorOutlined />}
                disabled={data.status === 'CLOSED'}
                onClick={() => setPricingOpen(true)}
              >
                新建核价
              </Button>
            </HasPermission>
            <HasPermission permission="quotation:create">
              <Button disabled={!latestApproved} onClick={generateQuotation}>
                由核价生成报价
              </Button>
            </HasPermission>
          </Space>
        }
      />

      <Card size="small" title="单据头" style={{ marginBottom: 16 }}>
        <Descriptions bordered size="small" column={4}>
          <Descriptions.Item label="状态">
            <StatusTag value={data.status} />
          </Descriptions.Item>
          <Descriptions.Item label="客户编号">{data.customer_code ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="客户名">{data.customer_name ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="新/老客户">
            {data.customer_type ? <Tag>{data.customer_type === 'NEW' ? '新' : '老'}</Tag> : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="部门">{data.department_name_text ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="业务员">{data.owner_name_text ?? data.owner_name ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="市场">{data.market ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="版本号">{data.version_no ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="发起时间">{formatDate(data.start_date)}</Descriptions.Item>
          <Descriptions.Item label="结束时间">{formatDate(data.end_date)}</Descriptions.Item>
          <Descriptions.Item label="样品可供时间">{formatDate(data.sample_date)}</Descriptions.Item>
          <Descriptions.Item label="交样周期">{data.sample_lead_time ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="下单时间">{formatDate(data.order_date)}</Descriptions.Item>
          <Descriptions.Item label="出货时间">{formatDate(data.shipment_date)}</Descriptions.Item>
          <Descriptions.Item label="首单货值（万）">
            {data.first_order_amount === null ? '-' : formatNumber(data.first_order_amount, 2)}
          </Descriptions.Item>
          <Descriptions.Item label="数量（个）">
            {data.quantity_total === null ? '-' : formatNumber(data.quantity_total)}
          </Descriptions.Item>
          <Descriptions.Item label="年金额">
            {data.annual_amount === null ? '-' : formatNumber(data.annual_amount, 2)}
          </Descriptions.Item>
          <Descriptions.Item label="创建时间" span={3}>
            {formatDateTime(data.created_at)}
          </Descriptions.Item>
          <Descriptions.Item label="需求说明" span={4}>
            <Typography.Text style={{ whiteSpace: 'pre-wrap' }}>
              {data.requirement_text ?? '-'}
            </Typography.Text>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card size="small" title="询价单填写模板（客户标准）" style={{ marginBottom: 16 }}>
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          纵向块：字段为行、产品为列。产品尺寸 / 显色指数 / 灯珠数量 / 功能 / 电线插头 /
          其他要求（含目标价与重启记录）等原始信息。
        </Typography.Paragraph>
        <Table
          size="small"
          bordered
          pagination={false}
          rowKey="label"
          dataSource={specRows}
          columns={[
            {
              title: '项目',
              dataIndex: 'label',
              width: 160,
              render: (v: string) => <b>{v}</b>,
            },
            ...Array.from({ length: specWidth }, (_v, i) => ({
              title: `产品 ${i + 1}`,
              key: `col-${i}`,
              render: (_: unknown, row: { label: string; values: string[] }) => (
                <Typography.Text style={{ whiteSpace: 'pre-wrap' }}>
                  {row.values?.[i] ?? ''}
                </Typography.Text>
              ),
            })),
          ]}
        />
      </Card>

      <Card size="small" title={`需开发产品 (${newItems.length})`} style={{ marginBottom: 16 }}>
        <Table<InquiryItem>
          rowKey={(r) => r.id ?? String(r.product_model)}
          size="small"
          bordered
          columns={ITEM_COLUMNS}
          dataSource={newItems}
          pagination={false}
          scroll={{ x: 2600 }}
        />
      </Card>

      <Card size="small" title={`已有产品 (${existingItems.length})`} style={{ marginBottom: 16 }}>
        <Table<InquiryItem>
          rowKey={(r) => r.id ?? String(r.product_model)}
          size="small"
          bordered
          columns={ITEM_COLUMNS}
          dataSource={existingItems}
          pagination={false}
          scroll={{ x: 2600 }}
        />
      </Card>

      <Card size="small" title="核价版本">
        <Table
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={versions.data ?? []}
          columns={[
            { title: '版本', dataIndex: 'version', width: 70, render: (v: number) => `V${v}` },
            {
              title: '状态',
              dataIndex: 'status',
              width: 120,
              render: (v: string) => <StatusTag value={v} />,
            },
            {
              title: '总成本',
              dataIndex: 'total_cost',
              width: 120,
              render: (v: number | null) => (v === null ? '***' : formatNumber(v, 2)),
            },
            {
              title: '底价',
              dataIndex: 'floor_price',
              width: 110,
              render: (v: number | null) => (v === null ? '***' : formatNumber(v, 4)),
            },
            {
              title: '最终价',
              dataIndex: 'final_price',
              width: 110,
              render: (v: number | null) => formatNumber(v, 2),
            },
            {
              title: '折扣率',
              dataIndex: 'discount_rate',
              width: 90,
              render: (v: number | null) => (v == null ? '1' : String(v)),
            },
            {
              title: '操作',
              width: 130,
              render: (_, row) => (
                <HasPermission permission="pricing:submit">
                  <Button
                    size="small"
                    disabled={row.status !== 'DRAFT'}
                    loading={submitPricing.isPending}
                    onClick={() => submitPricing.mutate(row.id)}
                  >
                    提交审批
                  </Button>
                </HasPermission>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title="新建核价（自动生成新版本）"
        open={pricingOpen}
        onCancel={() => setPricingOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createPricing.isPending}
        width={720}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ target_margin: 0.2, discount_rate: 1 }}
          onFinish={(v) => createPricing.mutate(v)}
        >
          <Row gutter={12}>
            {COST_FIELDS.map((f) => (
              <Col span={6} key={f.name}>
                <Form.Item name={f.name} label={f.label} initialValue={0}>
                  <InputNumber style={{ width: '100%' }} min={0} />
                </Form.Item>
              </Col>
            ))}
            <Col span={8}>
              <Form.Item name="target_margin" label="目标利润率（0.2 = 20%）">
                <InputNumber style={{ width: '100%' }} min={0} max={5} step={0.01} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="discount_rate" label="折扣率（∈(0,1]）">
                <InputNumber style={{ width: '100%' }} min={0.0001} max={1} step={0.01} />
              </Form.Item>
            </Col>
          </Row>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            底价 = 单位成本（零利润底线）；最终价 = 总成本 × (1 + 利润率) × 折扣率；折扣率 &lt;1 将触发经理/总监审批
          </Typography.Text>
        </Form>
      </Modal>
    </>
  );
}
