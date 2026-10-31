'use client';

import { ArrowLeftOutlined, SaveOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Empty, Form, Space } from 'antd';
import dayjs from 'dayjs';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { InquiryHeaderForm, InquiryItemBlocks, makeRow, type InquiryFormValues, type InquiryItemRow } from '@/components/business/InquiryForm';
import PageHeader from '@/components/common/PageHeader';
import { api } from '@/lib/api';
import type { PageResult } from '@/types';
import type { Company, Inquiry, InquiryItem } from '@/types/business';

type ItemRow = InquiryItemRow;

function toRows(items: InquiryItem[], group: 'NEW' | 'EXISTING'): ItemRow[] {
  return items
    .filter((i) => (i.group_type ?? 'EXISTING') === group)
    .map((i) => {
      const { id: _id, ...rest } = i;
      void _id;
      return makeRow(group, rest as Record<string, unknown>);
    });
}

const DATE_FIELDS: (keyof InquiryFormValues)[] = [
  'start_date',
  'end_date',
  'sample_date',
  'order_date',
  'shipment_date',
];

export default function EditInquiryPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id as string;
  const router = useRouter();
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const [form] = Form.useForm<InquiryFormValues>();
  const [newRows, setNewRows] = useState<ItemRow[]>([]);
  const [existingRows, setExistingRows] = useState<ItemRow[]>([]);
  const [loaded, setLoaded] = useState(false);

  const inquiry = useQuery({
    queryKey: ['inquiry', id],
    queryFn: () => api.get<Inquiry>(`/inquiries/${id}`),
    enabled: !!id,
  });

  const companies = useQuery({
    queryKey: ['company-options'],
    queryFn: () => api.get<PageResult<Company>>('/customers?page=1&page_size=500'),
  });

  useEffect(() => {
    if (!inquiry.data || loaded) return;
    const data = inquiry.data;
    const values: Record<string, unknown> = { ...data };
    DATE_FIELDS.forEach((key) => {
      const raw = data[key as keyof Inquiry] as string | null;
      values[key] = raw ? dayjs(raw) : null;
    });
    form.setFieldsValue(values as InquiryFormValues);
    setNewRows(toRows(data.items ?? [], 'NEW'));
    setExistingRows(toRows(data.items ?? [], 'EXISTING'));
    setLoaded(true);
  }, [inquiry.data, loaded, form]);

  const update = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.put(`/inquiries/${id}`, payload),
    onSuccess: () => {
      message.success('已保存');
      queryClient.invalidateQueries({ queryKey: ['inquiry', id] });
      queryClient.invalidateQueries({ queryKey: ['inquiries'] });
      router.replace(`/inquiries/${id}`);
    },
    onError: (e: Error) => message.error(e.message),
  });

  const submit = async () => {
    const values = await form.validateFields();
    const strip = (rows: ItemRow[]) =>
      rows
        .filter((r) => (r as { product_model?: string }).product_model)
        .map((row, index) => {
          const { _key, ...rest } = row;
          void _key;
          return { ...rest, sort: index + 1 };
        });
    const payload: Record<string, unknown> = {};
    Object.entries(values).forEach(([key, value]) => {
      if (DATE_FIELDS.includes(key as keyof InquiryFormValues)) {
        payload[key] = value ? dayjs(value as dayjs.Dayjs).format('YYYY-MM-DD') : null;
      } else {
        payload[key] = value;
      }
    });
    payload.items = [...strip(newRows), ...strip(existingRows)];
    update.mutate(payload);
  };

  if (!inquiry.data) {
    return <Empty description={inquiry.isFetching ? '加载中...' : '询价单不存在'} />;
  }

  return (
    <>
      <PageHeader
        title={`编辑 ${inquiry.data.inquiry_no}`}
        description="修改后覆盖保存（含明细）"
        extra={
          <Space>
            <Link href={`/inquiries/${id}`}>
              <Button icon={<ArrowLeftOutlined />}>返回详情</Button>
            </Link>
            <Button type="primary" icon={<SaveOutlined />} loading={update.isPending} onClick={submit}>
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
    </>
  );
}
