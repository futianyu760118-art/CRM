'use client';

import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import {
  Button,
  Card,
  Col,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Table,
  Tabs,
  Tooltip,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import type { ReactNode } from 'react';

import ImageUpload from '@/components/common/ImageUpload';
import type { Company } from '@/types/business';

export interface InquiryFormValues {
  company_id?: string | null;
  customer_code?: string | null;
  customer_name?: string | null;
  customer_type?: string | null;
  market?: string | null;
  department_name_text?: string | null;
  owner_name_text?: string | null;
  version_no?: string | null;
  start_date?: dayjs.Dayjs | null;
  end_date?: dayjs.Dayjs | null;
  sample_date?: dayjs.Dayjs | null;
  order_date?: dayjs.Dayjs | null;
  shipment_date?: dayjs.Dayjs | null;
  first_order_amount?: number | null;
  quantity_total?: number | null;
  annual_amount?: number | null;
  sample_lead_time?: string | null;
  currency?: string;
  requirement_text?: string | null;
}

export type InquiryItemRow = Record<string, unknown> & {
  _key: string;
  group_type: 'NEW' | 'EXISTING';
};

type Row = InquiryItemRow;

const TEXT_FIELDS: { name: string; label: string; width: number }[] = [
  { name: 'product_model', label: '产品型号', width: 150 },
  { name: 'product_name', label: '产品名称', width: 120 },
  { name: 'power', label: '功率', width: 80 },
  { name: 'voltage', label: '输入电压', width: 90 },
  { name: 'size', label: '产品尺寸', width: 100 },
  { name: 'battery', label: '电池', width: 100 },
  { name: 'color_temp', label: '色温', width: 80 },
  { name: 'cri', label: '显色指数', width: 90 },
  { name: 'lumen', label: '光通量/光效', width: 90 },
  { name: 'led_count', label: '灯珠数量', width: 90 },
  { name: 'light_source', label: '光源', width: 70 },
  { name: 'main_body', label: '主体', width: 80 },
  { name: 'lamp_shade', label: '灯罩', width: 80 },
  { name: 'reflector', label: '反光罩', width: 80 },
  { name: 'feature', label: '功能', width: 100 },
  { name: 'cable', label: '电缆线', width: 160 },
  { name: 'plug', label: '电线插头', width: 140 },
  { name: 'switch', label: '开关', width: 90 },
  { name: 'usb', label: 'USB', width: 80 },
  { name: 'waterproof', label: '防水等级', width: 80 },
  { name: 'sensor', label: '感应器', width: 130 },
  { name: 'other_requirement', label: '其他要求', width: 140 },
];

const EXISTING_EXTRA: { name: string; label: string; width: number }[] = [
  { name: 'frame', label: '压框', width: 80 },
  { name: 'other_requirement2', label: '其他要求2', width: 140 },
];

let seq = 0;
export function makeRow(group: 'NEW' | 'EXISTING', base: Partial<Row> = {}): Row {
  seq += 1;
  return { _key: `${group}-${seq}-${Date.now()}`, group_type: group, ...base } as Row;
}

function cell(
  rows: Row[],
  setRows: (next: Row[]) => void,
  field: string,
  width: number,
  label: string,
): ColumnsType<Row>[number] {
  return {
    title: label,
    dataIndex: field,
    width,
    render: (value: unknown, row) => (
      <Input
        size="small"
        variant="borderless"
        value={(value as string) ?? ''}
        onChange={(e) =>
          setRows(rows.map((r) => (r._key === row._key ? { ...r, [field]: e.target.value } : r)))
        }
      />
    ),
  };
}

interface Props {
  headerForm: ReactNode;
  newRows: Row[];
  existingRows: Row[];
  setNewRows: (rows: Row[]) => void;
  setExistingRows: (rows: Row[]) => void;
  disabled?: boolean;
}

export function InquiryItemBlocks({
  headerForm,
  newRows,
  existingRows,
  setNewRows,
  setExistingRows,
  disabled,
}: Props) {
  const buildColumns = (group: 'NEW' | 'EXISTING', rows: Row[], setRows: (r: Row[]) => void) => {
    const cols: ColumnsType<Row> = [
      {
        title: '序号',
        width: 54,
        align: 'center',
        render: (_v, _r, i) => i + 1,
      },
      {
        title: '产品图',
        dataIndex: 'image_file_id',
        width: 90,
        render: (value: string | null, row) => (
          <ImageUpload
            value={value}
            disabled={disabled}
            size={48}
            label="上传"
            onChange={(fileId) =>
              setRows(rows.map((r) => (r._key === row._key ? { ...r, image_file_id: fileId } : r)))
            }
          />
        ),
      },
    ];
    const fields = group === 'EXISTING'
      ? [
          TEXT_FIELDS[0]!,
          TEXT_FIELDS[1]!,
          TEXT_FIELDS[2]!,
          TEXT_FIELDS[3]!,
          TEXT_FIELDS[4]!,
          TEXT_FIELDS[5]!,
          TEXT_FIELDS[6]!,
          TEXT_FIELDS[7]!,
          TEXT_FIELDS[8]!,
          EXISTING_EXTRA[0]!,
          TEXT_FIELDS[9]!,
          TEXT_FIELDS[10]!,
          TEXT_FIELDS[11]!,
          TEXT_FIELDS[12]!,
          TEXT_FIELDS[13]!,
          TEXT_FIELDS[14]!,
          TEXT_FIELDS[15]!,
          EXISTING_EXTRA[1]!,
        ]
      : TEXT_FIELDS;

    fields.forEach((f) => cols.push(cell(rows, setRows, f.name, f.width, f.label)));

    cols.push(
      {
        title: group === 'NEW' ? '报价' : '报价',
        dataIndex: 'quote_price',
        width: 90,
        render: (value: number | null, row) => (
          <InputNumber
            size="small"
            variant="borderless"
            style={{ width: '100%' }}
            value={value ?? undefined}
            onChange={(v) =>
              setRows(rows.map((r) => (r._key === row._key ? { ...r, quote_price: v } : r)))
            }
            disabled={disabled}
          />
        ),
      },
    );
    if (group === 'NEW') {
      cols.push(
        {
          title: '目标价',
          dataIndex: 'target_price',
          width: 90,
          render: (value: number | null, row) => (
            <InputNumber
              size="small"
              variant="borderless"
              style={{ width: '100%' }}
              value={value ?? undefined}
              onChange={(v) =>
                setRows(rows.map((r) => (r._key === row._key ? { ...r, target_price: v } : r)))
              }
              disabled={disabled}
            />
          ),
        },
        {
          title: '需求数量',
          dataIndex: 'quantity',
          width: 90,
          render: (value: number | null, row) => (
            <InputNumber
              size="small"
              variant="borderless"
              style={{ width: '100%' }}
              value={value ?? undefined}
              onChange={(v) =>
                setRows(rows.map((r) => (r._key === row._key ? { ...r, quantity: v } : r)))
              }
              disabled={disabled}
            />
          ),
        },
        cell(rows, setRows, 'quote_lead_time', 100, '报价需时间'),
      );
    }
    cols.push({
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
    });
    return cols;
  };

  return (
    <>
      {headerForm}
      <Tabs
        style={{ marginTop: 12 }}
        items={[
          {
            key: 'NEW',
            label: `需开发产品 (${newRows.length})`,
            children: (
              <>
                <BlockToolbar
                  disabled={disabled}
                  onAdd={() =>
                    setNewRows([
                      ...newRows,
                      makeRow('NEW', { unit: 'PCS', quantity: 0, product_name: '' }),
                    ])
                  }
                />
                <Table<Row>
                  rowKey="_key"
                  size="small"
                  bordered
                  columns={buildColumns('NEW', newRows, setNewRows)}
                  dataSource={newRows}
                  pagination={false}
                  scroll={{ x: 2400 }}
                />
              </>
            ),
          },
          {
            key: 'EXISTING',
            label: `已有产品 (${existingRows.length})`,
            children: (
              <>
                <BlockToolbar
                  disabled={disabled}
                  onAdd={() =>
                    setExistingRows([
                      ...existingRows,
                      makeRow('EXISTING', { unit: 'PCS', quantity: 0, product_name: '' }),
                    ])
                  }
                />
                <Table<Row>
                  rowKey="_key"
                  size="small"
                  bordered
                  columns={buildColumns('EXISTING', existingRows, setExistingRows)}
                  dataSource={existingRows}
                  pagination={false}
                  scroll={{ x: 2300 }}
                />
              </>
            ),
          },
        ]}
      />
    </>
  );
}

function BlockToolbar({ onAdd, disabled }: { onAdd: () => void; disabled?: boolean }) {
  return (
    <Space style={{ marginBottom: 8 }}>
      <Button size="small" icon={<PlusOutlined />} onClick={onAdd} disabled={disabled}>
        添加行
      </Button>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        单元格可直接编辑；「产品图」点上传按钮选择图片
      </Typography.Text>
    </Space>
  );
}

// ------------------------------------------------------------------ 单据头表单

export function InquiryHeaderForm({
  form,
  companies,
  disabled,
}: {
  form: import('antd').FormInstance<InquiryFormValues>;
  companies: Company[];
  disabled?: boolean;
}) {
  const onPickCompany = (companyId: string) => {
    const company = companies.find((c) => c.id === companyId);
    if (company) {
      form.setFieldsValue({
        customer_code: company.code,
        customer_name: company.name,
      });
    }
  };

  return (
    <Card size="small" title="单据头">
      <Form form={form} layout="vertical" disabled={disabled}>
        <Row gutter={12}>
          <Col span={6}>
            <Form.Item name="company_id" label="关联客户">
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                placeholder="选择客户（自动带出编号与名称）"
                onChange={onPickCompany}
                options={companies.map((c) => ({ value: c.id, label: `${c.name}（${c.code}）` }))}
              />
            </Form.Item>
          </Col>
          <Col span={3}>
            <Form.Item name="customer_code" label="客户编号">
              <Input />
            </Form.Item>
          </Col>
          <Col span={5}>
            <Form.Item name="customer_name" label="客户名">
              <Input />
            </Form.Item>
          </Col>
          <Col span={3}>
            <Form.Item name="customer_type" label="新/老客户">
              <Select
                allowClear
                options={[
                  { value: 'NEW', label: '新' },
                  { value: 'OLD', label: '老' },
                ]}
              />
            </Form.Item>
          </Col>
          <Col span={3}>
            <Form.Item name="market" label="市场">
              <Input />
            </Form.Item>
          </Col>
          <Col span={4}>
            <Form.Item name="version_no" label="版本号">
              <Input placeholder="如 2025-08" />
            </Form.Item>
          </Col>

          <Col span={5}>
            <Form.Item name="department_name_text" label="部门">
              <Input placeholder="如 销售二部" />
            </Form.Item>
          </Col>
          <Col span={5}>
            <Form.Item name="owner_name_text" label="业务员">
              <Input placeholder="如 张三" />
            </Form.Item>
          </Col>
          <Col span={4}>
            <Form.Item name="sample_lead_time" label="交样周期">
              <Input />
            </Form.Item>
          </Col>
          <Col span={5}>
            <Form.Item name="start_date" label="发起时间">
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={5}>
            <Form.Item name="end_date" label="结束时间">
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
          </Col>

          <Col span={5}>
            <Form.Item name="sample_date" label="样品可供时间">
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={5}>
            <Form.Item name="order_date" label="下单时间">
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={5}>
            <Form.Item name="shipment_date" label="出货时间">
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={4}>
            <Form.Item name="first_order_amount" label="首单货值（万）">
              <InputNumber style={{ width: '100%' }} min={0} />
            </Form.Item>
          </Col>
          <Col span={4}>
            <Form.Item name="quantity_total" label="数量（个）">
              <InputNumber style={{ width: '100%' }} min={0} />
            </Form.Item>
          </Col>
          <Col span={4}>
            <Form.Item name="annual_amount" label="年金额">
              <InputNumber style={{ width: '100%' }} min={0} />
            </Form.Item>
          </Col>
          <Col span={24}>
            <Form.Item
              name="requirement_text"
              label={
                <Tooltip title="相同参数合并，和已经有过类似或者标准报价有差异点进行说明">
                  <span>需求说明</span>
                </Tooltip>
              }
            >
              <Input.TextArea rows={2} />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Card>
  );
}
