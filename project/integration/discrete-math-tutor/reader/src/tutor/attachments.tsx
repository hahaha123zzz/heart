import React from 'react';

// 附件和图片仍由宿主已核验的资源区提供，不接上游工作区操作。
export const useInlineFileCardContext = () => null;
export const makeFileLinkRemarkPlugin = () => null;
export const parseAttachmentHref = () => null;
export const InlineFileCard = ({fallback}: any) => <span>{fallback}</span>;
export const InlineWorkspaceImage = ({alt}: any) => <span>{alt}</span>;
