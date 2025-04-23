import { describe, test, expect } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/svelte';
import Page from './+page.svelte';

describe('/+page.svelte', () => {
	test('should render h1', () => {
		const mockData = {
			sites: [] // Provide a mock sites array
		};
		render(Page, { props: { data: mockData } });
		expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument();
	});
});
