// web/src/pages/carreira/Pdi.jsx
//
// Carreira · PDI. Esta entrega cria a aba; o PDI (ações sugeridas pelo
// Desempenho e pela Universidade, confirmadas pela gestão e acompanhadas
// pelo colaborador) é a próxima entrega. Até lá a aba explica o que vem e
// leva ao que já existe: o Desempenho, de onde as ações vão nascer.

import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowRight, Target } from 'lucide-react';
import PageHeader from '../../components/ui/PageHeader';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import AbasCarreira from '../../components/carreira/AbasCarreira';

export default function Pdi() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const usuarioId = params.get('usuario_id');
  const sufixo = usuarioId ? `?usuario_id=${encodeURIComponent(usuarioId)}` : '';

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <PageHeader title="Carreira" subtitle="Seu plano de desenvolvimento individual." />
      <AbasCarreira ativa="PDI" />
      <Card padding="lg">
        <div className="flex flex-col items-center text-center gap-3 py-6 max-w-xl mx-auto">
          <div className="w-12 h-12 rounded-full bg-hipo-blueSoft text-hipo-blue flex items-center justify-center">
            <Target size={22} aria-hidden="true" />
          </div>
          <h2 className="text-lg font-semibold text-hipo-ink">O PDI chega na próxima entrega</h2>
          <p className="text-sm text-hipo-slate">
            O HIPO vai sugerir ações a partir do seu Desempenho (indicador abaixo da meta, taxa de
            conversão fraca) e da Universidade (trilha atrasada). A gestão confirma ou ajusta com você,
            e cada ação tem objetivo, o que fazer, aula de reforço, prazo e situação.
          </p>
          <Button iconRight={ArrowRight} onClick={() => navigate(`/carreira/desempenho${sufixo}`)}>
            Ver o meu Desempenho
          </Button>
        </div>
      </Card>
    </div>
  );
}
