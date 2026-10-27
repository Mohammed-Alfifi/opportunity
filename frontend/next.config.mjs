/** @type {import('next').NextConfig} */
const nextConfig = {
  // واجهة ثابتة تخدمها الخلفية نفسها من نفس الأصل (حاوية واحدة على الاستضافة)
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
