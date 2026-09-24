'use client';

import { ArrowLeftOutlined, SaveOutlined } from '@ant-design/icons';
import { useMutation, useQuery } from '@tanstack/react-query';
import { App, Button, Form, Space, Typography } from 'antd';
import dayjs from 'dayjs';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import {
  InquiryHeaderForm,
  InquiryItemBlocks,
  makeRow,
  type InquiryFormValues,
  type InquiryItemRow,
} from '@/components/business/InquiryForm';
import PageHeader from '@/components/common/PageHeader';
import { api } from '@/lib/api';
import type { PageResult } from '@/types';
import type { Company, Inquiry } from '@/types/business';

export type ItemRow = InquiryItemRow;

const DATE_FIELDS: (keyof InquiryFormValues)[] = [
  'start_date',
  'end_date',
  'sample_date',
  'order_date',
  'shipment_date',
];

function buildPayload(values: InquiryFormValues, rows: InquiryItemRow[]) {
  const payload: Record<string, unknown> = {};
  Object.entries(values).forEach(([key, value]) => {
    if (DATE_FIELDS.includes(key as keyof InquiryFormValues)) {
      payload[key] = value ? dayjs(value as dayjs.Dayjs).format('YYYY-MM-DD') : null;
    } else if (value !== undefined) {
      payload[key] = value;
    }
  });
  payload.items = rows
    .filter((row) => row.product_model)
    .map((row, index) => {
      const { _key, ...rest } = row;
      void _key;
      return { ...rest, sort: index + 1 };
    });
  return payload;
}

export default function NewInquiryPage() {
  const router = useRouter();
  const { message } = App.useApp();
  const [form] = Form.useForm<InquiryFormValues>();
  const [newRows, setNewRows] = useState<InquiryItemRow[]>([
    makeRow('NEW', { unit: 'PCS', quantity: 0 }),
  ]);
  const [existingRows, setExistingRows] = useState<InquiryItemRow[]>([]);

  const companies = useQuery({
    queryKey: ['company-options'],
    queryFn: () => api.get<PageResult<Company>>('/customers?page=1&page_size=500'),
  });

  const create = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.post<Inquiry>('/inquiries', payload),
    onSuccess: (created) => {
      message.success(`询价单 ${created.inquiry_no} 创建成功`);
      router.replace(`/inquiries/${created.id}`);
    },
    onError: (e: Error) => message.error(e.message),
  });

  const submit = async () => {
    const values = await form.validateFields();
    const payload = buildPayload(values, [...newRows, ...existingRows]);
    if ((payload.items as unknown[]).length === 0) {
      message.warning('至少填写一条明细（产品型号）');
      return;
    }
    create.mutate({ ...payload, source: 'MANUAL', currency: 'RMB' });
  };

  return (
    <>
      <PageHeader
        title="新建询价单"
        description="按《客户询价单》模板填写：单据头 16 列 + 明细 22 列，分「需开发产品 / 已有产品」两组"
        extra={
          <Space>
            <Link href="/inquiries">
              <Button icon={<ArrowLeftOutlined />}>返回列表</Button>
            </Link>
            <Button type="primary" icon={<SaveOutlined />} loading={create.isPending} onClick={submit}>
              保存
            </Button>
          </Space>
        }
      />
      <InquiryItemBlocks
        headerForm={<InquiryHeaderForm form={form} companies={companies.data?.items ?? []} />}
        newRows={newRows}
        existingRows={existingRows}
        setNewRows={setNewRows}
        setExistingRows={setExistingRows}
      />
      <Typography.Paragraph type="secondary" style={{ marginTop: 12, fontSize: 12 }}>
        单号由系统按 JFX+日期+序号 规则自动生成。
      </Typography.Paragraph>
    </>
  );
}
