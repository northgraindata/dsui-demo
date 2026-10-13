const cookieName = "dsui_demo_visitor";
const validId =
	/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const existing = document.cookie
	.split(";")
	.map((part) => part.trim())
	.find((part) => part.startsWith(`${cookieName}=`))
	?.slice(cookieName.length + 1);

if (!existing || !validId.test(existing)) {
	const secure = location.protocol === "https:" ? "; Secure" : "";
	document.cookie = `${cookieName}=${crypto.randomUUID()}; Path=/; Max-Age=31536000; SameSite=Lax${secure}`;
}
