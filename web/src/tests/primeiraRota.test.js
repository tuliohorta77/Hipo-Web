// web/src/tests/primeiraRota.test.js
//
// primeiraRotaAcessivel: para onde o "/" manda cada cargo logo após o login.
// A conta de TV (cargo Monitor, só o módulo 'monitor') cai direto no painel.
import { describe, it, expect, afterEach } from 'vitest';
import { primeiraRotaAcessivel, USER_KEY } from '../api';

function logarCom(modulos) {
  localStorage.setItem(USER_KEY, JSON.stringify({ nome: 'x', modulos }));
}

afterEach(() => localStorage.clear());

describe('primeiraRotaAcessivel', () => {
  it('quem tem crm cai no funil', () => {
    logarCom(['perfil', 'crm']);
    expect(primeiraRotaAcessivel()).toBe('/crm/oportunidades');
  });

  it('a conta de TV cai no Monitor', () => {
    logarCom(['monitor']);
    expect(primeiraRotaAcessivel()).toBe('/monitor');
  });

  it('a conta da UC cai na Universidade', () => {
    logarCom(['uc']);
    expect(primeiraRotaAcessivel()).toBe('/uc');
  });

  it('a conta da administração (só contratos) cai em Contratos', () => {
    logarCom(['contratos']);
    expect(primeiraRotaAcessivel()).toBe('/contratos');
  });

  it('gestão com contratos continua caindo no funil', () => {
    logarCom(['perfil', 'crm', 'contratos']);
    expect(primeiraRotaAcessivel()).toBe('/crm/oportunidades');
  });

  it('sem módulo nenhum cai no Perfil', () => {
    logarCom([]);
    expect(primeiraRotaAcessivel()).toBe('/perfil');
  });
});
