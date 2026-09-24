import { Tag } from 'antd';
import type { ReactNode } from 'react';

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  // 线索
  NEW: { color: 'blue', label: '新建' },
  ASSIGNED: { color: 'cyan', label: '已分配' },
  CONVERTED: { color: 'green', label: '已转化' },
  INVALID: { color: 'default', label: '无效' },
  // 通用
  ACTIVE: { color: 'green', label: '正常' },
  INACTIVE: { color: 'default', label: '停用' },
  DISABLED: { color: 'default', label: '禁用' },
  BLACKLIST: { color: 'red', label: '黑名单' },
  // 商机
  QUALIFIED: { color: 'blue', label: '已确认' },
  REQUIREMENT: { color: 'blue', label: '需求明确' },
  INQUIRY: { color: 'geekblue', label: '询价中' },
  PRICING: { color: 'purple', label: '核价中' },
  QUOTATION: { color: 'magenta', label: '已报价' },
  SAMPLE: { color: 'orange', label: '样品阶段' },
  NEGOTIATION: { color: 'orange', label: '谈判中' },
  WON: { color: 'green', label: '赢单' },
  LOST: { color: 'red', label: '流失' },
  OPEN: { color: 'processing', label: '进行中' },
  CLOSED: { color: 'default', label: '已关闭' },
  // 询价
  DRAFT: { color: 'default', label: '草稿' },
  SUBMITTED: { color: 'blue', label: '已提交' },
  PRICED: { color: 'purple', label: '已核价' },
  QUOTED: { color: 'magenta', label: '已报价' },
  // 报价 / 审批
  PENDING_APPROVAL: { color: 'gold', label: '待审批' },
  APPROVED: { color: 'green', label: '已通过' },
  REJECTED: { color: 'red', label: '已驳回' },
  SENT: { color: 'cyan', label: '已发送' },
  ACCEPTED: { color: 'green', label: '已接受' },
  EXPIRED: { color: 'default', label: '已过期' },
  PENDING: { color: 'gold', label: '待处理' },
  SUCCESS: { color: 'green', label: '成功' },
  FAILED: { color: 'red', label: '失败' },
  SKIPPED: { color: 'default', label: '已跳过' },
  RETRYING: { color: 'orange', label: '重试中' },
  PROCESSING: { color: 'blue', label: '处理中' },
  // 任务
  DONE: { color: 'green', label: '已完成' },
  CANCELLED: { color: 'default', label: '已取消' },
  // 邮件
  SENT_DIRECTION: { color: 'blue', label: '发件' },
  RECEIVED: { color: 'green', label: '收件' },
  SIMULATED: { color: 'orange', label: '模拟发送' },
  // 优先级
  HIGH: { color: 'red', label: '高' },
  MEDIUM: { color: 'blue', label: '中' },
  LOW: { color: 'default', label: '低' },
};

export function statusLabel(value: string | null | undefined): string {
  if (!value) return '-';
  return STATUS_MAP[value]?.label ?? value;
}

interface Props {
  value: string | null | undefined;
  color?: string;
  label?: string;
  children?: ReactNode;
}

export function StatusTag({ value, color, label, children }: Props) {
  if (!value) return <Tag>-</Tag>;
  const mapped = STATUS_MAP[value];
  return <Tag color={color ?? mapped?.color ?? 'default'}>{children ?? label ?? mapped?.label ?? value}</Tag>;
}

export default StatusTag;
