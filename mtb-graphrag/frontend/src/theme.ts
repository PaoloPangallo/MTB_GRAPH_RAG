import { createTheme } from '@mui/material/styles';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1E40AF',
      light: '#DBEAFE',
      dark: '#1E3A8A',
    },
    secondary: {
      main: '#0F766E',
      light: '#CCFBF1',
    },
    background: {
      default: '#F8FAFC',
      paper: '#FFFFFF',
    },
    text: {
      primary: '#0F172A',
      secondary: '#475569',
    },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h1: { fontSize: '2rem', fontWeight: 700, color: '#1E293B', letterSpacing: '-0.02em' },
    h2: { fontSize: '1.5rem', fontWeight: 700, color: '#1E293B', letterSpacing: '-0.01em' },
    h3: { fontSize: '1.25rem', fontWeight: 600, color: '#1E293B' },
    h4: { fontSize: '1.1rem', fontWeight: 600, color: '#1E293B' },
    h5: { fontSize: '1rem', fontWeight: 600, color: '#1E293B' },
    h6: { fontSize: '0.95rem', fontWeight: 600, color: '#1E293B' },
    body1: { fontSize: '0.95rem', lineHeight: 1.7 },
    body2: { fontSize: '0.875rem', lineHeight: 1.6 },
    caption: { fontSize: '0.75rem', lineHeight: 1.4, color: '#64748B' },
  },
  shape: {
    borderRadius: 8,
  },
  components: {
    MuiAppBar: {
      styleOverrides: {
        root: {
          background: 'linear-gradient(135deg, #1E3A8A 0%, #1E40AF 100%)',
          boxShadow: '0 2px 8px rgba(30, 58, 138, 0.35)',
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          boxShadow: '0 1px 4px 0 rgb(0 0 0 / 0.07), 0 2px 8px -1px rgb(0 0 0 / 0.06)',
          border: '1px solid #E2E8F0',
          borderRadius: 10,
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 600,
          borderRadius: 8,
          letterSpacing: '0.01em',
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          fontWeight: 500,
          borderRadius: 6,
        },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 500,
          fontSize: '0.875rem',
          minHeight: 48,
        },
      },
    },
    MuiTableHead: {
      styleOverrides: {
        root: {
          '& .MuiTableCell-root': {
            fontWeight: 700,
            fontSize: '0.72rem',
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: '#64748B',
            backgroundColor: '#F1F5F9',
            borderBottom: '2px solid #E2E8F0',
          },
        },
      },
    },
    MuiTableBody: {
      styleOverrides: {
        root: {
          '& .MuiTableRow-root': {
            '&:nth-of-type(odd)': {
              backgroundColor: '#F8FAFC',
            },
            '&:hover': {
              backgroundColor: '#EFF6FF',
            },
          },
          '& .MuiTableCell-root': {
            verticalAlign: 'top',
            padding: '10px 16px',
          },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
        },
      },
    },
    MuiTabs: {
      styleOverrides: {
        indicator: {
          height: 3,
          borderRadius: '3px 3px 0 0',
        },
      },
    },
  },
});

export default theme;
