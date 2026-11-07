import pytest


@pytest.mark.asyncio
async def test_product_slug_history_resolves_and_reserves_old_urls(client, admin_headers):
    created = await client.post('/api/v1/admin/products', headers=admin_headers, json={
        'name': 'Wallet', 'slug': 'first-wallet', 'description': 'Leather', 'price': 100,
        'canonicalUrl': 'https://wrenza.com/products/first-wallet',
    })
    assert created.status_code == 200, created.text
    pid = created.json()['id']
    for slug in ('second-wallet', 'third-wallet'):
        response = await client.put(f'/api/v1/admin/products/{pid}', headers=admin_headers, json={'slug': slug})
        assert response.status_code == 200, response.text
        assert response.json()['canonicalUrl'] == f'https://wrenza.com/products/{slug}'
    for old in ('first-wallet', 'second-wallet'):
        result = await client.get(f'/api/v1/products/slug-redirect/{old}')
        assert result.status_code == 200
        assert result.json()['slug'] == 'third-wallet'
        detail = await client.get(f'/api/v1/products/{old}')
        assert detail.json()['slug'] == 'third-wallet'
    other = await client.post('/api/v1/admin/products', headers=admin_headers, json={
        'name': 'Other', 'slug': 'first-wallet', 'description': 'Leather', 'price': 100,
    })
    assert other.status_code == 200, other.text
    assert other.json()['slug'] != 'first-wallet'
    restored = await client.put(f'/api/v1/admin/products/{pid}', headers=admin_headers, json={'slug': 'first-wallet'})
    assert restored.status_code == 200, restored.text
    assert restored.json()['slug'] == 'first-wallet'
    assert (await client.get('/api/v1/products/slug-redirect/first-wallet')).status_code == 404
    assert (await client.get('/api/v1/products/slug-redirect/third-wallet')).json()['slug'] == 'first-wallet'


@pytest.mark.asyncio
async def test_inactive_product_does_not_redirect(client, admin_headers):
    created = await client.post('/api/v1/admin/products', headers=admin_headers, json={
        'name': 'Wallet', 'slug': 'old-wallet', 'description': 'Leather', 'price': 100,
    })
    pid = created.json()['id']
    await client.put(f'/api/v1/admin/products/{pid}', headers=admin_headers, json={'slug': 'new-wallet'})
    await client.put(f'/api/v1/admin/products/{pid}', headers=admin_headers, json={'isActive': False})
    assert (await client.get('/api/v1/products/slug-redirect/old-wallet')).status_code == 404
    assert (await client.get('/api/v1/products/old-wallet')).status_code == 404
