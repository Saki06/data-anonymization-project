'use client';

import Link from 'next/link';

export default function Breadcrumb({ label = '← Back to Home', href = '/' }: { label?: string; href?: string }) {
  return (
    <div className="breadcrumb">
      <Link href={href}>{label}</Link>
    </div>
  );
}
