'use client';

import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Form, Input, InputNumber, Modal, Select, Space, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { api, buildQuery } from '@/lib/api';
import { formatMoney } from '@/lib/format';
import type { PageResult } from '@/types';
import type { Product, Sku } from '@/types/business';

export default function ProductsPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [productOpen, setProductOpen] = useState(false);
  const [skuProduct, setSkuProduct] = useState<Product | null>(null);
  const [productForm] = Form.useForm();
  const [skuForm] = Form.useForm();

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['products', page, keyword],
    queryFn: () =>
      api.get<PageResult<Product>>(`/products${buildQuery({ page, page_size: 10, keyword })}`),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['products'] });

  const createProduct = useMutation({
    mutationFn: (values: Record<string, unknown>) => api.post('/products', values),
    onSuccess: () => {
      message.success('产品创建成功');
      setProductOpen(false);
      productForm.resetFields();
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const createSku = useMutation({
    mutationFn: (values: Record<string, unknown>) =>
      api.post(`/products/${skuProduct?.id}/skus`, values),
    onSuccess: () => {
      message.success('SKU 已添加');
      setSkuProduct(null);
      skuForm.resetFields();
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const columns: ColumnsType<Product> = [
    { title: '产品编码', dataIndex: 'code', width: 130 },
    { title: '产品名称', dataIndex: 'name', ellipsis: true },
    { title: '英文名称', dataIndex: 'name_en', ellipsis: true, render: (v) => v ?? '-' },
    { title: '类别', dataIndex: 'category', width: 110, render: (v) => v ?? '-' },
    { title: '单位', dataIndex: 'unit', width: 80 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (v: string) => <StatusTag value={v} />,
    },
    {
      title: 'SKU 明细',
      render: (_, row) =>
        row.skus.length === 0 ? (
          <Tag>无</Tag>
        ) : (
          <Space size={[4, 4]} wrap>
            {row.skus.map((s: Sku) => (
              <Tag key={s.id} color="blue">
                {s.code} · {formatMoney(s.price, s.currency)}
              </Tag>
            ))}
          </Space>
        ),
    },
    {
      title: '操作',
      width: 110,
      render: (_, row) => (
        <HasPermission permission="product:update">
          <Button size="small" onClick={() => setSkuProduct(row)}>
            加 SKU
          </Button>
        </HasPermission>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="产品 / SKU 管理"
        description="产品与 SKU 维护，供询价与报价引用（对应 F-10）"
        extra={
          <Space>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="编码/名称/类别"
              style={{ width: 200 }}
              onPressEnter={(e) => {
                setPage(1);
                setKeyword((e.target as HTMLInputElement).value);
              }}
            />
            <Button icon={<ReloadOutlined />} onClick={() => refetch()} />
            <HasPermission permission="product:create">
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setProductOpen(true)}>
                新建产品
              </Button>
            </HasPermission>
          </Space>
        }
      />

      <Table<Product>
        rowKey="id"
        size="small"
        loading={isFetching}
        columns={columns}
        dataSource={data?.items ?? []}
        scroll={{ x: 1100 }}
        pagination={{
          current: data?.page ?? 1,
          pageSize: data?.page_size ?? 10,
          total: data?.total ?? 0,
          onChange: setPage,
        }}
      />

      <Modal
        title="新建产品"
        open={productOpen}
        onCancel={() => setProductOpen(false)}
        onOk={() => productForm.submit()}
        confirmLoading={createProduct.isPending}
        destroyOnClose
      >
        <Form form={productForm} layout="vertical" onFinish={(v) => createProduct.mutate(v)}>
          <Form.Item name="code" label="产品编码" rules={[{ required: true }]}>
            <Input placeholder="如 P-1001" />
          </Form.Item>
          <Form.Item name="name" label="产品名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="name_en" label="英文名称">
            <Input />
          </Form.Item>
          <Form.Item name="category" label="类别">
            <Input />
          </Form.Item>
          <Form.Item name="unit" label="单位" initialValue="PCS">
            <Select
              options={['PCS', 'SET', 'KG', 'M', 'CTN'].map((v) => ({ value: v, label: v }))}
            />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`添加 SKU - ${skuProduct?.name ?? ''}`}
        open={!!skuProduct}
        onCancel={() => setSkuProduct(null)}
        onOk={() => skuForm.submit()}
        confirmLoading={createSku.isPending}
        destroyOnClose
      >
        <Form form={skuForm} layout="vertical" onFinish={(v) => createSku.mutate(v)}>
          <Form.Item name="code" label="SKU 编码" rules={[{ required: true }]}>
            <Input placeholder="如 P-1001-500" />
          </Form.Item>
          <Form.Item name="spec" label="规格">
            <Input placeholder="如 500ml / 304 双层真空" />
          </Form.Item>
          <Form.Item name="unit" label="单位" initialValue={skuProduct?.unit ?? 'PCS'}>
            <Input />
          </Form.Item>
          <Form.Item name="price" label="参考价">
            <InputNumber style={{ width: '100%' }} min={0} />
          </Form.Item>
          <Form.Item name="cost" label="成本">
            <InputNumber style={{ width: '100%' }} min={0} />
          </Form.Item>
          <Form.Item name="currency" label="币种" initialValue="USD">
            <Select options={['USD', 'EUR', 'CNY'].map((v) => ({ value: v, label: v }))} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
