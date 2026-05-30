import { Profile } from "@/components/bv/web/Profile";

export default function Page({ params }: { params: { slug: string } }) {
  return <Profile slug={params.slug} />;
}
