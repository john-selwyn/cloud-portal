# Screenshots on the Ubuntu Server release

Before = `7fa0023` (deployed baseline). After = `4783e90` (PR #9 head, `7fa0023` + the two cleanup commits).
Preview database: throwaway SQLite, migrations through 0013, `UBUNTU_SERVER_ORDERING_ENABLED=True`, placeholder data, one Ubuntu Server order (`orders/5`, `vps/5`). Desktop 1440px, phone 390px.

Pixel comparison (>8/255 per channel):

| Page | Desktop | Phone |
|---|---|---|
| Checkout `plans/1/` (lists Ubuntu Server 26.04 LTS) | identical | 0.61% (new mobile header) |
| Ubuntu VPS detail `vps/5/` | identical | 0.40% (header) |
| Ubuntu order `orders/5/` | identical | 0.78% (header) |
| Order provisioning status | identical | identical |
| Payment return / cancel | identical | 0.97% (header) |
| Staff pages (`management/`, services, login) | identical | identical |
| Dashboard, My VPS, Orders, Invoices, Account, VPS Plans, Web Hosting | changed by design (page height differs) | changed by design |
