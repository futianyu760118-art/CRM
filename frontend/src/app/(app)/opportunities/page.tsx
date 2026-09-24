'use client';

import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App,
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Table,
  Tooltip,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import Link from 'next/link';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { api, buildQuery } from '@/lib/api';
import { formatMoney } from '@/lib/format';
import type { PageResult } from '@/types';
import type { Company, KanbanColumn, Opportunity } from '@/types/business';

export default function OpportunitiesPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [view, setView] = useState<'kanban' | 'list'>('kanban');
  const [createOpen, setCreateOpen] = useState(false);
  const [form] = Form.useForm();

  const kanban = useQuery({
    queryKey: ['opportunities-kanban'],
    queryFn: () => api.get<{ columns: KanbanColumn[] }>('/opportunities/kanban'),
  });

  const list = useQuery({
    queryKey: ['opportunities-list'],
    queryFn: () =>
      api.get<PageResult<Opportunity>>(`/opportunities${buildQuery({ page: 1, page_size: 100 })}`),
  });

  const companies = useQuery({
    queryKey: ['company-options'],
    queryFn: () => api.get<PageResult<Company>>('/customers?page=1&page_size=200'),
  });

  const createMutation = useMutation({
    mutationFn: (values: Record<string, unknown>) => api.post('/opportunities', values),
    onSuccess: () => {
      message.success('商机创建成功');
      setCreateOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['opportunities-kanban'] });
      queryClient.invalidateQueries({ queryKey: ['opportunities-list'] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  const columns: ColumnsType<Opportunity> = [
    {
      title: '商机编号',
      dataIndex: 'opportunity_no',
      width: 170,
      render: (v: string, row) => <Link href={`/opportunities/${row.id}`}>{v}</Link>,
    },
    { title: '商机名称', dataIndex: 'name', ellipsis: true },
    { title: '客户', dataIndex: 'company_name', width: 200, render: (v) => v ?? '-' },
    {
      title: '阶段',
      dataIndex: 'stage',
      width: 120,
      render: (v: string) => <StatusTag value={v} />,
    },
    {
      title: '预计金额',
      dataIndex: 'estimated_amount',
      width: 160,
      render: (v: number | null, row) => formatMoney(v, row.currency),
    },
    { title: '概率', dataIndex: 'probability', width: 80, render: (v) => (v ? `${v}%` : '-') },
  ];

  const kanbanColumns = kanban.data?.columns ?? [];

  return (
    <>
      <PageHeader
        title="商机管理"
        description="看板视图 + 列表视图，阶段流转由状态机约束（对应 F-08、F-09）"
        extra={
          <Space>
            <Segmented
              value={view}
              onChange={(v) => setView(v as 'kanban' | 'list')}
              options={[
                { label: '看板', value: 'kanban' },
                { label: '列表', value: 'list' },
              ]}
            />
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                kanban.refetch();
                list.refetch();
              }}
            />
            <HasPermission permission="opportunity:create">
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
                新建商机
              </Button>
            </HasPermission>
          </Space>
        }
      />

      {view === 'kanban' ? (
        <div style={{ overflowX: 'auto', paddingBottom: 8 }}>
          <div style={{ display: 'flex', gap: 12, minWidth: 1400 }}>
            {kanbanColumns.map((col) => (
              <div key={col.stage} style={{ width: 220, flex: '0 0 auto' }}>
                <Card
                  size="small"
                  title={
                    <Space size={6}>
                      <StatusTag value={col.stage} />
                      <span style={{ fontSize: 12, color: '#999' }}>{col.count}</span>
                    </Space>
                  }
                  styles={{ body: { padding: 8, minHeight: 120, background: '#fafafa' } }}
                >
                  <Statistic
                    value={col.amount}
                    precision={2}
                    valueStyle={{ fontSize: 13 }}
                    prefix="$"
                  />
                  <div style={{ marginTop: 8 }}>
                    <Space direction="vertical" size={6} style={{ width: '100%' }}>
                      {col.cards.map((card) => (
                        <Link key={card.id} href={`/opportunities/${card.id}`}>
                          <Card size="small" hoverable styles={{ body: { padding: 8 } }}>
                            <Tooltip title={card.name}>
                              <div
                                style={{
                                  fontSize: 13,
                                  fontWeight: 500,
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap',
                                }}
                              >
                                {card.name}
                              </div>
                            </Tooltip>
                            <div style={{ fontSize: 12, color: '#888' }}>
                              {card.company_name ?? '-'}
                            </div>
                            <div style={{ fontSize: 12, color: '#1677ff' }}>
                              {formatMoney(card.estimated_amount, card.currency)}
                            </div>
                          </Card>
                        </Link>
                      ))}
                      {col.cards.length === 0 ? (
                        <div style={{ fontSize: 12, color: '#bbb', textAlign: 'center' }}>
                          暂无商机
                        </div>
                      ) : null}
                    </Space>
                  </div>
                </Card>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <Table<Opportunity>
          rowKey="id"
          size="small"
          loading={list.isFetching}
          columns={columns}
          dataSource={list.data?.items ?? []}
          pagination={{ pageSize: 20 }}
        />
      )}

      <Modal
        title="新建商机"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending}
        destroyOnClose
        width={640}
      >
        <Form form={form} layout="vertical" requiredMark={false} onFinish={(v) => createMutation.mutate(v)}>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="name" label="商机名称" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="company_id" label="客户" rules={[{ required: true }]}>
                <Select
                  showSearch
                  optionFilterProp="label"
                  placeholder="选择客户"
                  options={(companies.data?.items ?? []).map((c) => ({
                    value: c.id,
                    label: c.name,
                  }))}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="estimated_amount" label="预计金额">
                <InputNumber style={{ width: '100%' }} min={0} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="currency" label="币种" initialValue="USD">
                <Select
                  options={['USD', 'EUR', 'CNY'].map((v) => ({ value: v, label: v }))}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="probability" label="成交概率(%)">
                <InputNumber style={{ width: '100%' }} min={0} max={100} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="product_category" label="产品类别">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="quantity" label="数量">
                <InputNumber style={{ width: '100%' }} min={0} />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="requirement" label="需求描述">
                <Input.TextArea rows={3} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </>
  );
}
