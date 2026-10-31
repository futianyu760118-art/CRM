'use client';

import { ArrowLeftOutlined, SaveOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Card, Empty, Form, Space } from 'antd';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import {
  QuotationHeaderForm,
  QuotationItemTable,
  QuotationNotesForm,
  makeQuoteRow,
  termsToText,
  textToTerms,
  type QuotationFormValues,
  type QuoteRow,
} from '@/components/business/QuotationForm';
import PageHeader from '@/components/common/PageHeader';
import { api } from '@/lib/api';
import type { PageResult } from '@/types';
import type { Company, Quotation } from '@/types/business';

export default function EditQuotationPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id as string;
  const router = useRouter();
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const [form] = Form.useForm<QuotationFormValues>();
  const [rows, setRows] = useState<QuoteRow[]>([]);
  const [currency, setCurrency] = useState('RMB');
  const [loaded, setLoaded] = useState(false);

  const quotation = useQuery({
    queryKey: ['quotation', id],
    queryFn: () => api.get<Quotation>(`/quotations/${id}`),
    enabled: !!id,
  });

  const companies = useQuery({
    queryKey: ['company-options'],
    queryFn: () => api.get<PageResult<Company>>('/customers?page=1&page_size=500'),
  });

  useEffect(() => {
    if (!quotation.data || loaded) return;
    const data = quotation.data;
    form.setFieldsValue({
      company_id: data.company_id,
      buyer_attn: data.buyer_attn ?? undefined,
      title: data.title ?? 'Offer',
      currency: data.currency,
      valid_days: data.valid_days,
      incoterm: data.incoterm ?? undefined,
      payment_terms: data.payment_terms ?? undefined,
      warranty: data.warranty ?? undefined,
      seller_name: data.seller_name ?? undefined,
      seller_address: data.seller_address ?? undefined,
      seller_contact: data.seller_contact ?? undefined,
      remark: data.remark ?? undefined,
      terms: termsToText(data.terms),
      notes_cn: data.notes_cn ?? undefined,
      notes_en: data.notes_en ?? undefined,
    });
    setCurrency(data.currency);
    setRows(
      (data.items ?? []).map((item) => {
        const { id: _id, amount: _amount, ...rest } = item;
        void _id;
        void _amount;
        return makeQuoteRow(rest as Record<string, unknown>);
      }),
    );
    setLoaded(true);
  }, [quotation.data, loaded, form]);

  const update = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.put(`/quotations/${id}`, payload),
    onSuccess: () => {
      message.success('已保存');
      queryClient.invalidateQueries({ queryKey: ['quotation', id] });
      queryClient.invalidateQueries({ queryKey: ['quotations'] });
      router.replace(`/quotations/${id}`);
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
    const { terms, ...rest } = values;
    update.mutate({ ...rest, terms: textToTerms(terms), items });
  };

  if (!quotation.data) {
    return <Empty description={quotation.isFetching ? '加载中...' : '报价单不存在'} />;
  }

  return (
    <Form form={form} layout="vertical">
      <PageHeader
        title={`编辑 ${quotation.data.quotation_no}`}
        description={`${quotation.data.company_name ?? ''} · 状态 ${quotation.data.status}`}
        extra={
          <Space>
            <Link href={`/quotations/${id}`}>
              <Button icon={<ArrowLeftOutlined />}>返回详情</Button>
            </Link>
            <Button type="primary" icon={<SaveOutlined />} loading={update.isPending} onClick={submit}>
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
