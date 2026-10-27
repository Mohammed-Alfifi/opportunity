import { Suspense } from "react";
import JobView from "./JobView";

// تصدير ثابت: صفحة واحدة تقرأ رقم الوظيفة من ?id= بدل مسار ديناميكي يحتاج خادم Next
export default function JobPage() {
  return (
    <Suspense fallback={<p className="muted">جارٍ التحميل…</p>}>
      <JobView />
    </Suspense>
  );
}
