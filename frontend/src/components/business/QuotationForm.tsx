'use client';

import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import {
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Table,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { ReactNode } from 'react';

import ImageUpload from '@/components/common/ImageUpload';
import { buildQuery } from '@/lib/api';
import type { Company } from '@/types/business';

export interface QuotationFormValues {
  company_id?: string;
  buyer_attn?: string;
  title?: string;
  currency?: string;
  incoterm?: string;
  payment_terms?: string;
  warranty?: string;
  valid_days?: number;
  seller_name?: string;
  seller_address?: string;
  seller_contact?: string;
  terms?: string;
  notes_cn?: string;
  notes_en?: string;
  remark?: string;
}

export type QuoteRow = Record<string, unknown> & { _key: string };

let seq = 0;
export function makeQuoteRow(base: Partial<QuoteRow> = {}): QuoteRow {
  seq += 1;
  return { _key: `q-${seq}-${Date.now()}`, unit_price: 0, ...base } as QuoteRow;
}

const TEXT_COLUMNS: { name: string; label: string; width: number }[] = [
  { name: 'item_no', label: 'Item No.', width: 150 },
  { name: 'description', label: 'Description of Goods', width: 340 },
  { name: 'moq', label: 'MOQ', width: 90 },
  { name: 'power', label: 'Power (W)', width: 90 },
  { name: 'ip', label: 'IP', width: 70 },
  { name: 'lumen', label: 'Lumen (lm)', width: 100 },
  { name: 'color_temp', label: 'Color TEMP.', width: 110 },
  { name: 'color_rendering', label: 'Color Rendering (Ra)', width: 130 },
  { name: 'price_valid', label: 'Price Valid', width: 110 },
];

export function QuotationItemTable({
  rows,
  setRows,
  currency,
  disabled,
}: {
  rows: QuoteRow[];
  setRows: (rows: QuoteRow[]) => void;
  currency: string;
  disabled?: boolean;
}) {
  const update = (key: string, field: string, value: unknown) =>
    setRows(rows.map((r) => (r._key === key ? { ...r, [field]: value } : r)));

  const columns: ColumnsType<QuoteRow> = [
    {
      title: '#',
      width: 46,
      align: 'center',
      render: (_v, _r, i) => i + 1,
    },
    {
      title: 'Picture',
      dataIndex: 'image_file_id',
      width: 90,
      render: (value: string | null, row) => (
        <ImageUpload
          value={value}
          size={48}
          disabled={disabled}
          label="上传"
          onChange={(fileId) => update(row._key, 'image_file_id', fileId)}
        />
      ),
    },
    ...TEXT_COLUMNS.slice(0, 2).map((c) => ({
      title: c.label,
      dataIndex: c.name,
      width: c.width,
      render: (value: unknown, row: QuoteRow) =>
        c.name === 'description' ? (
          <Input.TextArea
            size="small"
            autoSize={{ minRows: 2, maxRows: 6 }}
            value={(value as string) ?? ''}
            disabled={disabled}
            onChange={(e) => update(row._key, c.name, e.target.value)}
          />
        ) : (
          <Input
            size="small"
            variant="borderless"
            value={(value as string) ?? ''}
            disabled={disabled}
            onChange={(e) => update(row._key, c.name, e.target.value)}
          />
        ),
    })),
    {
      title: `Price (${currency})`,
      dataIndex: 'unit_price',
      width: 110,
      render: (value: number, row) => (
        <InputNumber
          size="small"
          variant="borderless"
          style={{ width: '100%' }}
          value={value}
          disabled={disabled}
          onChange={(v) => update(row._key, 'unit_price', v ?? 0)}
        />
      ),
    },
    ...TEXT_COLUMNS.slice(2).map((c) => ({
      title: c.label,
      dataIndex: c.name,
      width: c.width,
      render: (value: unknown, row: QuoteRow) => (
        <Input
          size="small"
          variant="borderless"
          value={(value as string) ?? ''}
          disabled={disabled}
          onChange={(e) => update(row._key, c.name, e.target.value)}
        />
      ),
    })),
    {
      title: '',
      width: 50,
      fixed: 'right',
      render: (_v, row) => (
        <Button
          size="small"
          type="text"
          danger
          icon={<DeleteOutlined />}
          disabled={disabled}
          onClick={() => setRows(rows.filter((r) => r._key !== row._key))}
        />
      ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 8 }}>
        <Button
          size="small"
          icon={<PlusOutlined />}
          disabled={disabled}
          onClick={() => setRows([...rows, makeQuoteRow()])}
        >
          添加产品行
        </Button>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Description 可换行；Picture 上传产品图后会嵌入 Excel / PDF
        </Typography.Text>
      </Space>
      <Table<QuoteRow>
        rowKey="_key"
        size="small"
        bordered
        columns={columns}
        dataSource={rows}
        pagination={false}
        scroll={{ x: 1900 }}
      />
    </>
  );
}

export function QuotationHeaderForm({
  companies,
  disabled,
  currency,
  onCurrencyChange,
}: {
  companies: Company[];
  disabled?: boolean;
  currency: string;
  onCurrencyChange?: (value: string) => void;
}) {
  return (
    <Card
      size="small"
      title="报价单信息"
      extra={<span style={{ fontSize: 12, color: '#999' }}>Excel / PDF 导出的抬头与条款</span>}
    >
      <Row gutter={12}>
        <Col span={8}>
          <Form.Item name="company_id" label="客户" rules={[{ required: true, message: '请选择客户' }]}>
            <Select
              disabled={disabled}
              showSearch
              optionFilterProp="label"
              options={companies.map((c) => ({ value: c.id, label: `${c.name}（${c.code}）` }))}
            />
          </Form.Item>
        </Col>
        <Col span={4}>
          <Form.Item name="buyer_attn" label="Attn.">
            <Input disabled={disabled} />
          </Form.Item>
        </Col>
        <Col span={6}>
          <Form.Item name="title" label="标题" tooltip="如 Work Light offer">
            <Input placeholder="Offer" disabled={disabled} />
          </Form.Item>
        </Col>
        <Col span={3}>
          <Form.Item name="currency" label="币种">
            <Select
              disabled={disabled}
              onChange={onCurrencyChange}
              options={['RMB', 'USD', 'EUR', 'CNY'].map((v) => ({ value: v, label: v }))}
            />
          </Form.Item>
        </Col>
        <Col span={3}>
          <Form.Item name="valid_days" label="有效期(天)">
            <InputNumber style={{ width: '100%' }} min={1} disabled={disabled} />
          </Form.Item>
        </Col>

        <Col span={8}>
          <Form.Item name="seller_name" label="卖方抬头">
            <Input disabled={disabled} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="seller_address" label="Add: 地址">
            <Input disabled={disabled} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="seller_contact" label="Email / Website">
            <Input disabled={disabled} />
          </Form.Item>
        </Col>

        <Col span={8}>
          <Form.Item name="incoterm" label="贸易术语">
            <Input placeholder="FOB NINGBO" disabled={disabled} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="payment_terms" label="付款条件">
            <Input disabled={disabled} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="warranty" label="质保">
            <Input placeholder="Two Years" disabled={disabled} />
          </Form.Item>
        </Col>

        <Col span={24}>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} disabled={disabled} />
          </Form.Item>
        </Col>
      </Row>
    </Card>
  );
}

export function termsToText(terms: string[] | null | undefined): string {
  return (terms ?? []).join('\n');
}

export function textToTerms(text: string | undefined): string[] {
  return (text ?? '')
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);
}

export const COMPANY_OPTIONS_PATH = (pageSize = 500) =>
  `/customers${buildQuery({ page: 1, page_size: pageSize })}`;

export function QuotationNotesForm({ disabled }: { disabled?: boolean }) {
  return (
    <Card size="small" title="条款与说明" style={{ marginTop: 16 }}>
      <Form.Item name="terms" label="▲ 条款（每行一条，导出时逐行输出）">
        <Input.TextArea rows={6} disabled={disabled} />
      </Form.Item>
      <Form.Item name="notes_cn" label="中文说明">
        <Input.TextArea rows={5} disabled={disabled} />
      </Form.Item>
      <Form.Item name="notes_en" label="英文说明">
        <Input.TextArea rows={4} disabled={disabled} />
      </Form.Item>
    </Card>
  );
}

export type { ReactNode };
