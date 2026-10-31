'use client';

import { DeleteOutlined, PlusOutlined, ReloadOutlined, SearchOutlined, UploadOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App,
  Button,
  DatePicker,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { api, buildQuery, fileUrl, uploadForm as uploadMultipart } from '@/lib/api';
import {
  CURRENCY_OPTIONS,
  PRODUCT_DOC_TYPE_OPTIONS,
  PRODUCT_DOC_TYPES,
  QUOTE_STATUS_LABELS,
} from '@/lib/dictionaries';
import { formatDate, formatDateTime, formatMoney } from '@/lib/format';
import type { PageResult } from '@/types';
import type {
  Product,
  ProductDocument,
  ProductDocumentGroup,
  Sku,
  StandardQuote,
} from '@/types/business';

function formatSize(size: number): string {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  if (size >= 1024) return `${(size / 1024).toFixed(0)} KB`;
  return `${size} B`;
}

interface QuoteFormValues {
  currency: string;
  qty_from: number;
  qty_to?: number | null;
  unit_price: number;
  valid_from: dayjs.Dayjs;
  valid_to: dayjs.Dayjs;
  version_no: string;
}

export default function ProductsPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [productOpen, setProductOpen] = useState(false);
  const [skuProduct, setSkuProduct] = useState<Product | null>(null);
  const [assetProduct, setAssetProduct] = useState<Product | null>(null);
  const [docUpload, setDocUpload] = useState<{ doc_type: string; version_no?: string }>({
    doc_type: 'SALES_MATERIAL',
  });
  const [quoteOpen, setQuoteOpen] = useState(false);
  const [selectedQuote, setSelectedQuote] = useState<StandardQuote | null>(null);
  const [productForm] = Form.useForm();
  const [skuForm] = Form.useForm();
  const [quoteForm] = Form.useForm<QuoteFormValues>();
  const [selectForm] = Form.useForm<{ currency: string; quantity: number }>();

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

  // ---------------------------------------------------------------- 产品资料
  const documents = useQuery({
    queryKey: ['product-documents', assetProduct?.id],
    queryFn: () => api.get<ProductDocumentGroup[]>(`/products/${assetProduct!.id}/documents`),
    enabled: !!assetProduct,
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append('file', file);
      form.append('doc_type', docUpload.doc_type);
      if (docUpload.version_no?.trim()) form.append('version_no', docUpload.version_no.trim());
      return uploadMultipart<ProductDocument>(`/products/${assetProduct!.id}/documents`, form);
    },
    onSuccess: () => {
      message.success('资料已上传');
      queryClient.invalidateQueries({ queryKey: ['product-documents', assetProduct?.id] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  const deleteDocument = useMutation({
    mutationFn: (doc: ProductDocument) => api.delete(`/products/${assetProduct!.id}/documents/${doc.id}`),
    onSuccess: () => {
      message.success('资料已删除');
      queryClient.invalidateQueries({ queryKey: ['product-documents', assetProduct?.id] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  const docColumns: ColumnsType<ProductDocument> = [
    {
      title: '文件名',
      dataIndex: 'filename',
      ellipsis: true,
      render: (_, row) => (
        <a href={fileUrl(row.file_id)} target="_blank" rel="noreferrer">
          {row.filename}
        </a>
      ),
    },
    {
      title: '版本号',
      dataIndex: 'version_no',
      width: 110,
      render: (v: string, row) => (
        <Space size={4}>
          <span>{v}</span>
          {row.is_current ? <Tag color="green">当前有效</Tag> : <Tag>历史</Tag>}
        </Space>
      ),
    },
    { title: '大小', dataIndex: 'size', width: 90, render: (v: number) => formatSize(v) },
    { title: '上传人', dataIndex: 'uploader_name', width: 100, render: (v) => v ?? '-' },
    { title: '上传时间', dataIndex: 'created_at', width: 160, render: (v) => formatDateTime(v) },
    {
      title: '',
      width: 70,
      render: (_, row) => (
        <HasPermission permission="product:update">
          <Popconfirm title="删除该资料？删除后剩余最高版本自动成为当前有效。" onConfirm={() => deleteDocument.mutate(row)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </HasPermission>
      ),
    },
  ];

  const quoteStatusColor: Record<string, string> = {
    ACTIVE: 'green',
    EXPIRED: 'default',
    PENDING: 'blue',
    DISABLED: 'red',
  };

  const quotes = useQuery({
    queryKey: ['standard-quotes', assetProduct?.id],
    queryFn: () => api.get<StandardQuote[]>(`/products/${assetProduct!.id}/standard-quotes`),
    enabled: !!assetProduct,
  });

  const createQuote = useMutation({
    mutationFn: (values: QuoteFormValues) => {
      const payload = {
        ...values,
        valid_from: values.valid_from.format('YYYY-MM-DD'),
        valid_to: values.valid_to.format('YYYY-MM-DD'),
      };
      return api.post(`/products/${assetProduct!.id}/standard-quotes`, payload);
    },
    onSuccess: () => {
      message.success('标准报价已创建');
      setQuoteOpen(false);
      quoteForm.resetFields();
      queryClient.invalidateQueries({ queryKey: ['standard-quotes', assetProduct?.id] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  const disableQuote = useMutation({
    mutationFn: (quote: StandardQuote) => api.post(`/standard-quotes/${quote.id}/disable`),
    onSuccess: () => {
      message.success('标准报价已停用');
      queryClient.invalidateQueries({ queryKey: ['standard-quotes', assetProduct?.id] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  const selectQuote = useMutation({
    mutationFn: (values: { currency: string; quantity: number }) =>
      api.post<StandardQuote>(`/products/${assetProduct!.id}/standard-quotes/select`, values),
    onSuccess: (quote) => {
      setSelectedQuote(quote);
      message.success(`适用单价：${quote.currency_label} ${quote.unit_price}（版本 ${quote.version_no}）`);
    },
    onError: (e: Error) => {
      setSelectedQuote(null);
      message.error(e.message);
    },
  });

  const quoteColumns: ColumnsType<StandardQuote> = [
    { title: '币种', dataIndex: 'currency_label', width: 90 },
    { title: '数量区间', dataIndex: 'interval_label', width: 140 },
    {
      title: '单价',
      dataIndex: 'unit_price',
      width: 120,
      render: (v: number, row) => formatMoney(v, row.currency),
    },
    {
      title: '有效期',
      width: 200,
      render: (_, row) => `${formatDate(row.valid_from)} ~ ${formatDate(row.valid_to)}`,
    },
    { title: '版本', dataIndex: 'version_no', width: 80 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: string, row) => <Tag color={quoteStatusColor[v]}>{row.status_label || QUOTE_STATUS_LABELS[v] || v}</Tag>,
    },
    {
      title: '',
      width: 80,
      render: (_, row) =>
        row.status === 'DISABLED' ? null : (
          <HasPermission permission="product:update">
            <Popconfirm title="停用后不可改价，只能新建版本。确认停用？" onConfirm={() => disableQuote.mutate(row)}>
              <Button type="link" size="small" danger>
                停用
              </Button>
            </Popconfirm>
          </HasPermission>
        ),
    },
  ];

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
      width: 190,
      render: (_, row) => (
        <Space size={0}>
          <Button size="small" type="link" onClick={() => setAssetProduct(row)}>
            产品资料
          </Button>
          <HasPermission permission="product:update">
            <Button size="small" type="link" onClick={() => setSkuProduct(row)}>
              加 SKU
            </Button>
          </HasPermission>
        </Space>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="产品 / SKU 管理"
        description="产品与 SKU 维护，含销售资料 / 规格书 / 测试报告 / 认证文件与标准报价（PAND-316）"
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
            <Select options={CURRENCY_OPTIONS} />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={`产品资料 - ${assetProduct?.name ?? ''}`}
        open={!!assetProduct}
        onClose={() => setAssetProduct(null)}
        width={860}
        destroyOnClose
      >
        <Tabs
          items={[
            {
              key: 'documents',
              label: '文件资料',
              children: (
                <>
                  <Space wrap style={{ marginBottom: 12 }}>
                    <Select
                      value={docUpload.doc_type}
                      style={{ width: 140 }}
                      options={PRODUCT_DOC_TYPE_OPTIONS}
                      onChange={(doc_type) => setDocUpload((s) => ({ ...s, doc_type }))}
                    />
                    <Input
                      placeholder="版本号（留空自动生成 v1）"
                      style={{ width: 200 }}
                      value={docUpload.version_no}
                      onChange={(e) => setDocUpload((s) => ({ ...s, version_no: e.target.value }))}
                    />
                    <HasPermission permission="product:update">
                      <Upload
                        showUploadList={false}
                        maxCount={1}
                        beforeUpload={(file) => {
                          uploadMutation.mutate(file as File);
                          return false;
                        }}
                      >
                        <Button type="primary" icon={<UploadOutlined />} loading={uploadMutation.isPending}>
                          上传（≤50MB）
                        </Button>
                      </Upload>
                    </HasPermission>
                    <Typography.Text type="secondary">
                      支持 pdf/doc/docx/xls/xlsx/ppt/pptx/jpg/jpeg/png/zip
                    </Typography.Text>
                  </Space>
                  {documents.isLoading ? (
                    <Empty description="加载中..." />
                  ) : (
                    PRODUCT_DOC_TYPE_OPTIONS.map((opt) => {
                      const group = (documents.data ?? []).find((g) => g.doc_type === opt.value);
                      return (
                        <div key={opt.value} style={{ marginBottom: 16 }}>
                          <Typography.Text strong>
                            {PRODUCT_DOC_TYPES[opt.value]}（{group?.count ?? 0} 份）
                          </Typography.Text>
                          {group?.latest_version ? (
                            <Typography.Text type="secondary">
                              {' '}
                              · 最新版本 {group.latest_version}
                            </Typography.Text>
                          ) : null}
                          <Table<ProductDocument>
                            rowKey="id"
                            size="small"
                            style={{ marginTop: 8 }}
                            columns={docColumns}
                            dataSource={group?.documents ?? []}
                            pagination={false}
                            locale={{ emptyText: `暂无${PRODUCT_DOC_TYPES[opt.value]}` }}
                          />
                        </div>
                      );
                    })
                  )}
                </>
              ),
            },
            {
              key: 'quotes',
              label: '标准报价',
              children: (
                <>
                  <Space wrap style={{ marginBottom: 12 }}>
                    <HasPermission permission="product:update">
                      <Button type="primary" icon={<PlusOutlined />} onClick={() => setQuoteOpen(true)}>
                        新建标准报价
                      </Button>
                    </HasPermission>
                    <Select
                      style={{ width: 110 }}
                      defaultValue="USD"
                      options={CURRENCY_OPTIONS}
                      onChange={(currency) => selectForm.setFieldValue('currency', currency)}
                    />
                    <InputNumber
                      min={1}
                      placeholder="数量"
                      style={{ width: 120 }}
                      onChange={(quantity) => selectForm.setFieldValue('quantity', quantity ?? 1)}
                    />
                    <Button
                      loading={selectQuote.isPending}
                      onClick={() =>
                        selectForm
                          .validateFields()
                          .then((v) => selectQuote.mutate(v))
                          .catch(() => undefined)
                      }
                    >
                      查询适用单价
                    </Button>
                    {selectedQuote ? (
                      <Tag color="green">
                        {selectedQuote.interval_label} · {formatMoney(selectedQuote.unit_price, selectedQuote.currency)}
                      </Tag>
                    ) : null}
                  </Space>
                  <Form form={selectForm} initialValues={{ currency: 'USD', quantity: 1 }} style={{ display: 'none' }}>
                    <Form.Item name="currency">
                      <Input />
                    </Form.Item>
                    <Form.Item name="quantity">
                      <InputNumber />
                    </Form.Item>
                  </Form>
                  <Table<StandardQuote>
                    rowKey="id"
                    size="small"
                    loading={quotes.isFetching}
                    columns={quoteColumns}
                    dataSource={quotes.data ?? []}
                    pagination={false}
                    locale={{ emptyText: '暂无标准报价' }}
                  />
                </>
              ),
            },
          ]}
        />
      </Drawer>

      <Modal
        title="新建标准报价"
        open={quoteOpen}
        onCancel={() => setQuoteOpen(false)}
        onOk={() => quoteForm.submit()}
        confirmLoading={createQuote.isPending}
        destroyOnClose
        width={560}
      >
        <Form form={quoteForm} layout="vertical" onFinish={(v) => createQuote.mutate(v)}>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="currency" label="币种" initialValue="USD" rules={[{ required: true }]}>
              <Select style={{ width: 120 }} options={CURRENCY_OPTIONS} />
            </Form.Item>
            <Form.Item name="version_no" label="版本号" initialValue="v1" rules={[{ required: true }]}>
              <Input style={{ width: 140 }} placeholder="如 v1 / v1.2" />
            </Form.Item>
          </Space>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="qty_from" label="数量条件（起，含）" rules={[{ required: true }]}>
              <InputNumber min={1} style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="qty_to" label="数量条件（止，不含）">
              <InputNumber min={2} style={{ width: 160 }} placeholder="留空表示无上限" />
            </Form.Item>
            <Form.Item name="unit_price" label="单价" rules={[{ required: true }]}>
              <InputNumber min={0.0001} precision={4} style={{ width: 140 }} />
            </Form.Item>
          </Space>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="valid_from" label="有效期（起）" rules={[{ required: true }]}>
              <DatePicker style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="valid_to" label="有效期（止）" rules={[{ required: true }]}>
              <DatePicker style={{ width: 160 }} />
            </Form.Item>
          </Space>
          <Typography.Text type="secondary">
            同产品同币种的数量区间不得重叠；已生效报价不可改价，只能停用后新建版本。
          </Typography.Text>
        </Form>
      </Modal>
    </>
  );
}
