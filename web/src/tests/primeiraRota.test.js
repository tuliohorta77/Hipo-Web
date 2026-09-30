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

  it('sem módulo nenhum cai no Perfil', () => {
    logarCom([]);
    expect(primeiraRotaAcessivel()).toBe('/perfil');
  });
});
