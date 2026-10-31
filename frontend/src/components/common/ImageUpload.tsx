'use client';

import { DeleteOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons';
import { App, Button, Image, Space, Upload } from 'antd';
import type { UploadFile as AntUploadFile } from 'antd/es/upload/interface';
import { useState } from 'react';

import { fileUrl, uploadFile } from '@/lib/api';

interface Props {
  value?: string | null;
  onChange?: (fileId: string | null) => void;
  disabled?: boolean;
  size?: number;
  label?: string;
}

/** 单图上传：value 为 file_id，自动渲染缩略图与预览。 */
export function ImageUpload({ value, onChange, disabled, size = 64, label = '图片' }: Props) {
  const { message } = App.useApp();
  const [uploading, setUploading] = useState(false);

  const handle = async (file: File) => {
    setUploading(true);
    try {
      const uploaded = await uploadFile(file, 'product');
      onChange?.(uploaded.id);
      message.success('图片已上传');
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const fileList: AntUploadFile[] = value
    ? [{ uid: value, name: 'image', status: 'done', url: fileUrl(value) }]
    : [];

  return (
    <Space size={4} direction="vertical">
      {value ? (
        <Image
          src={fileUrl(value)}
          alt={label}
          width={size}
          height={size}
          style={{ objectFit: 'cover' }}
        />
      ) : null}
      <Space size={4}>
        <Upload
          accept="image/*"
          showUploadList={false}
          disabled={disabled || uploading}
          beforeUpload={(file) => {
            void handle(file as unknown as File);
            return false;
          }}
        >
          <Button size="small" icon={<UploadOutlined />} loading={uploading} disabled={disabled}>
            {value ? '替换' : label}
          </Button>
        </Upload>
        {value ? (
          <Button
            size="small"
            type="text"
            danger
            icon={<DeleteOutlined />}
            disabled={disabled}
            onClick={() => onChange?.(null)}
          />
        ) : null}
      </Space>
      {fileList.length === 0 ? null : null}
    </Space>
  );
}

export default ImageUpload;

export const ImageUploadAddIcon = PlusOutlined;
