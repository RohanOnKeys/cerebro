export function MockDataBanner() {
  return (
    <div className="border-b border-cerebro-accent-light bg-cerebro-bg-raised px-8 py-3">
      <p className="text-sm text-cerebro-accent-lightest">
        Showing sample data. Set CEREBRO_API_BASE_URL and CEREBRO_ADMIN_API_TOKEN
        to connect the live Admin/Read API.
      </p>
    </div>
  );
}
