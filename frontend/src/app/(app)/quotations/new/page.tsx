'use client';

import { ArrowLeftOutlined, SaveOutlined } from '@ant-design/icons';
import { useMutation, useQuery } from '@tanstack/react-query';
import { App, Button, Card, Form, Space } from 'antd';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import {
  QuotationHeaderForm,
  QuotationItemTable,
  QuotationNotesForm,
  makeQuoteRow,
  textToTerms,
  type QuotationFormValues,
  type QuoteRow,
} from '@/components/business/QuotationForm';
import PageHeader from '@/components/common/PageHeader';
import { api } from '@/lib/api';
import type { PageResult } from '@/types';
import type { Company, Quotation } from '@/types/business';

const DEFAULT_TERMS = [
  '▲ Remarks：Price validity: 30 days from the date of quotation. This quotation is based on current raw material costs. Final price will be reconfirmed at the time of order confirmation.',
  '▲ If qty less than 1000pcs, extra start-up costs ￥800/ model',
  '▲ Color customized costs ￥2000/ model',
  '▲ FOB NINGBO',
  '▲ Payment term: 30% T/T in advance and the balance 70% should be settled on sight of B/L copy',
  '▲ Warranty: Two Years',
];

const DEFAULT_NOTES_CN = `1.本报价基于以下标准配置:标准包装(彩盒+A4黑白说明书+黑字黄包)、标准起订量(1000个)、无特殊认证、无定制要求。
2.如有特殊需求(彩盒、贴牌、认证、低于起订量、定制规格等)，需另行报价。
3.本报价有效期:30天(自报价之日起)。
4.正式订单下达前，请双方再次确认所有需求与报价单一致。如有变更，需重新报价。`;

const DEFAULT_NOTES_EN = `Pricing basis: The above prices are for the basic color box + yellow outer carton with black printed text + A4 black-and-white instruction manual.
For any special packaging requirements, such as hardening or thickening, or custom requests like product logo silk-screen printing, please contact us separately to discuss the price difference.`;

export default function NewQuotationPage() {
  const router = useRouter();
  const { message } = App.useApp();
  const [form] = Form.useForm<QuotationFormValues>();
  const [rows, setRows] = useState<QuoteRow[]>([makeQuoteRow()]);
  const [currency, setCurrency] = useState('RMB');

  const companies = useQuery({
    queryKey: ['company-options'],
    queryFn: () => api.get<PageResult<Company>>('/customers?page=1&page_size=500'),
  });

  const create = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.post<Quotation>('/quotations', payload),
    onSuccess: (created) => {
      message.success(`报价单 ${created.quotation_no} 创建成功`);
      router.replace(`/quotations/${created.id}`);
    },
    onError: (e: Error) => message.error(e.message),
  });

  const submit = async () => {
    const values = await form.validateFields();
    const items = rows
      .filter((r) => r.item_no || r.description)
      .map((row, index) => {
        const { _key, ...rest } = row;
        void _key;
        return { ...rest, sort: index + 1, product_name: String(row.item_no ?? '') };
      });
    if (items.length === 0) {
      message.warning('至少填写一条产品行（Item No. 或 Description）');
      return;
    }
    const { terms, ...rest } = values;
    create.mutate({
      ...rest,
      currency: values.currency ?? 'RMB',
      terms: textToTerms(terms),
      items,
    });
  };

  return (
    <Form
      form={form}
      layout="vertical"
      initialValues={{
        currency: 'RMB',
        valid_days: 30,
        title: 'Offer',
        terms: DEFAULT_TERMS.join('\n'),
        notes_cn: DEFAULT_NOTES_CN,
        notes_en: DEFAULT_NOTES_EN,
      }}
    >
      <PageHeader
        title="新建报价单"
        description="对外英文价格表：抬头 + Item No./Picture/Description/Price/MOQ/规格列 + 条款 + 中英说明"
        extra={
          <Space>
            <Link href="/quotations">
              <Button icon={<ArrowLeftOutlined />}>返回列表</Button>
            </Link>
            <Button type="primary" icon={<SaveOutlined />} loading={create.isPending} onClick={submit}>
              保存
            </Button>
          </Space>
        }
      />
      <QuotationHeaderForm
        companies={companies.data?.items ?? []}
        currency={currency}
        onCurrencyChange={setCurrency}
      />
      <Card style={{ marginTop: 16 }}>
        <QuotationItemTable rows={rows} setRows={setRows} currency={currency} />
      </Card>
      <QuotationNotesForm />
    </Form>
  );
}
